package com.diary.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.Dish
import com.diary.net.DishBody
import com.diary.net.DishPatch
import com.diary.net.FoodData
import com.diary.net.ImageHit
import com.diary.net.IngredientsData
import com.diary.net.versionPoll
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json

private val lenientJson = Json { ignoreUnknownKeys = true }

/** Parses a dish's canonical ingredients JSON (see api/services/food.py's
 *  _validate_ingredients_json) -- "" or malformed text is not a dish's
 *  fault to crash over, it just means "no ingredients yet". */
fun parseIngredients(raw: String): IngredientsData {
    if (raw.isBlank()) return IngredientsData()
    return runCatching { lenientJson.decodeFromString<IngredientsData>(raw) }.getOrDefault(IngredientsData())
}

/** One line in the shopping list: an ingredient name, optionally split by
 *  unit when two recipes measure it differently (grams vs a bare count, say)
 *  -- those can't be added together. `approximate` marks a line where some
 *  OTHER recipe also uses this ingredient but didn't give an amount at all,
 *  so the true total is at least this much. Mirrors FoodPanel.tsx's
 *  GroceryTotal / computeGroceryTotals. */
data class GroceryTotal(
    val key: String, // "name::unit" -- also the sum key for same-name-same-unit amounts
    val name: String,
    val unit: String,
    val amount: Double?, // null only when every contributor gave no quantity
    val approximate: Boolean,
)

fun computeGroceryTotals(dishes: List<Dish>, list: Map<Int, Int>): List<GroceryTotal> {
    data class Acc(val byUnit: MutableMap<String, Double> = mutableMapOf(), var hasUnspecified: Boolean = false)
    val byName = LinkedHashMap<String, Acc>()
    val byId = dishes.associateBy { it.id }

    for ((id, targetQty) in list) {
        val dish = byId[id] ?: continue
        val parsed = parseIngredients(dish.ingredients)
        val baseQty = parsed.quantity.toDoubleOrNull()
        // No sane base to scale from (missing/zero/non-numeric) -> take the
        // recipe's amounts as-is rather than blow up on a division by zero.
        val factor = if (baseQty != null && baseQty > 0) targetQty / baseQty else 1.0
        for ((rawName, entry) in parsed.ingredients) {
            val name = rawName.trim()
            if (name.isEmpty()) continue
            val unit = entry.unit.trim()
            val acc = byName.getOrPut(name) { Acc() }
            val qty = entry.quantity.trim()
            if (qty.isEmpty()) {
                acc.hasUnspecified = true
                continue
            }
            val n = qty.toDoubleOrNull() ?: continue
            acc.byUnit[unit] = (acc.byUnit[unit] ?: 0.0) + n * factor
        }
    }

    val totals = mutableListOf<GroceryTotal>()
    for ((name, acc) in byName) {
        if (acc.byUnit.isEmpty()) {
            totals.add(GroceryTotal("$name::", name, "", null, false))
            continue
        }
        for ((unit, amount) in acc.byUnit) {
            totals.add(GroceryTotal("$name::$unit", name, unit, amount, acc.hasUnspecified))
        }
    }
    return totals.sortedBy { it.name }
}

/** Food catalogue state, plus the grocery list (a purely client-side
 *  convenience persisted in [Prefs], never sent to the backend -- mirrors
 *  grocery.ts). Load / version-poll-guard / snapshot-reply pattern is the
 *  same as [PersonalViewModel]. */
class FoodViewModel : ViewModel() {
    var data by mutableStateOf<FoodData?>(null); private set
    var error by mutableStateOf<String?>(null); private set

    var groceryList by mutableStateOf<Map<Int, Int>>(Prefs.loadGroceryList()); private set
    var checkedIngredients by mutableStateOf<Set<String>>(Prefs.loadCheckedIngredients()); private set

    private var appliedVersion = -1
    private var seenFood = 0

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v ->
                if (v.food == seenFood) return@collect
                seenFood = v.food
                if (data != null && v.food != appliedVersion) load()
            }
        }
    }

    private fun load() = viewModelScope.launch {
        runCatching { Api.foodDishes() }
            .onSuccess { apply(it) }
            .onFailure { error = it.message }
    }

    private fun apply(d: FoodData) {
        data = d
        appliedVersion = d.version
        error = null
        pruneGroceryList(d)
    }

    // Drop grocery-list entries for dishes that got deleted, or whose
    // ingredients got cleared out from under it -- otherwise a stale id
    // could sit in prefs forever pointing at nothing.
    private fun pruneGroceryList(d: FoodData) {
        val eligible = d.dishes.filter { it.ingredients.isNotBlank() }.map { it.id }.toSet()
        val next = groceryList.filterKeys { it in eligible }
        if (next.size != groceryList.size) {
            groceryList = next
            Prefs.saveGroceryList(next)
            resetChecked()
        }
    }

    private fun mutate(block: suspend () -> FoodData) = viewModelScope.launch {
        runCatching { block() }
            .onSuccess { apply(it) }
            .onFailure { error = it.message }
    }

    fun addDish(body: DishBody) = mutate { Api.addDish(body) }
    fun patchDish(id: Int, patch: DishPatch) = mutate { Api.patchDish(id, patch) }
    fun deleteDish(id: Int) = mutate { Api.deleteDish(id) }

    /** One-shot image search for the picker; result delivered via callback so
     *  the composable can hold it in local state. */
    fun searchImages(query: String, onResult: (List<ImageHit>) -> Unit, onError: (String) -> Unit) {
        viewModelScope.launch {
            runCatching { Api.searchDishImages(query) }
                .onSuccess { onResult(it.images) }
                .onFailure { onError(it.message ?: "search failed") }
        }
    }

    // ── grocery list ─────────────────────────────────────────────────────
    // Checked-off shopping-list lines are only meaningful for the exact
    // selection/quantities that produced them -- any change to either wipes
    // them rather than carrying stale checks forward.
    private fun resetChecked() {
        checkedIngredients = emptySet()
        Prefs.saveCheckedIngredients(emptySet())
    }

    /** Replaces the whole selection at once (id -> quantity), defaulting a
     *  newly-added dish to its own recipe quantity if it has one, else 1 --
     *  mirrors FoodPanel.tsx's confirmSelection. */
    fun setGrocerySelection(ids: Set<Int>) {
        val next = ids.associateWith { id ->
            groceryList[id]?.let { return@associateWith it }
            val dish = data?.dishes?.firstOrNull { it.id == id }
            val base = dish?.let { parseIngredients(it.ingredients).quantity.toDoubleOrNull() }
            if (base != null && base > 0) base.toInt().coerceAtLeast(1) else 1
        }
        groceryList = next
        Prefs.saveGroceryList(next)
        resetChecked()
    }

    fun setGroceryQty(id: Int, qty: Int) {
        val next = groceryList + (id to qty.coerceAtLeast(1))
        groceryList = next
        Prefs.saveGroceryList(next)
        resetChecked()
    }

    fun removeFromGrocery(id: Int) {
        val next = groceryList - id
        groceryList = next
        Prefs.saveGroceryList(next)
        resetChecked()
    }

    fun clearGroceryList() {
        groceryList = emptyMap()
        Prefs.saveGroceryList(emptyMap())
        resetChecked()
    }

    fun toggleChecked(key: String) {
        val next = if (key in checkedIngredients) checkedIngredients - key else checkedIngredients + key
        checkedIngredients = next
        Prefs.saveCheckedIngredients(next)
    }
}
