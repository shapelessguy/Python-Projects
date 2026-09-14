@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import coil.request.ImageRequest
import com.diary.Prefs
import com.diary.net.Api
import com.diary.net.Dish
import com.diary.net.DishBody
import com.diary.net.DishPatch
import com.diary.net.FoodImages
import com.diary.net.ImageHit
import com.diary.net.IngredientEntry
import com.diary.net.IngredientsData
import kotlinx.serialization.json.Json
import kotlin.math.roundToInt

/** Card width at the min-zoom end — sets how many columns you can fan out to.
 *  Wide enough that the footer's rating + 4 action icons still fit on one line. */
private const val MIN_CARD_DP = 180
private val Gold = Color(0xFFF2C14E)

/**
 * Column count for the food grid. `zoom` is 0f (min) … 1f (max). At max zoom the
 * grid shows 2 columns when the viewport is wider than tall, 1 when it's taller
 * than wide; at min zoom it fans out to however many [MIN_CARD_DP]-wide columns
 * fit. The slider interpolates between those.
 */
private fun columnCount(zoom: Float, widthDp: Int, heightDp: Int): Int {
    val minCols = if (widthDp >= heightDp) 2 else 1
    val maxCols = maxOf(minCols, widthDp / MIN_CARD_DP)
    return (maxCols - zoom * (maxCols - minCols)).roundToInt().coerceIn(minCols, maxCols)
}

private fun stars(rating: Int): String {
    val n = rating.coerceIn(0, 10)
    return if (n == 0) "—" else "★".repeat(n) + " ($n)"
}

private fun ratingShort(rating: Int): String =
    if (rating <= 0) "—" else "★ $rating"

private fun formatAmount(n: Double): String {
    val r = Math.round(n * 100) / 100.0
    return if (r == r.toLong().toDouble()) r.toLong().toString() else r.toString()
}

private sealed interface Editing {
    data object New : Editing
    data class Existing(val dish: Dish) : Editing
}

@Composable
fun FoodScreen(vm: FoodViewModel = viewModel()) {
    val data = vm.data
    var editing by remember { mutableStateOf<Editing?>(null) }
    var confirmDeleteId by remember { mutableStateOf<Int?>(null) }
    var editingInstructions by remember { mutableStateOf<Dish?>(null) }
    var editingIngredients by remember { mutableStateOf<Dish?>(null) }
    // 0f = min zoom (many small columns) … 1f = max zoom (1–2 columns).
    var zoom by remember { mutableStateOf((Prefs.foodZoomPct.coerceIn(0, 100)) / 100f) }

    var groceryMode by remember { mutableStateOf(false) }
    var pendingSelection by remember { mutableStateOf<Set<Int>>(emptySet()) }

    val cfg = LocalConfiguration.current
    val columns = columnCount(zoom, cfg.screenWidthDp, cfg.screenHeightDp)

    // Categories start collapsed. `expanded` = open ones, `everOpened` gates
    // whether a category's cards are mounted at all (nothing downloads until
    // opened), `loadedCats` marks the ones whose images have all settled — they
    // skip the progress bar afterwards.
    val expanded = remember { mutableStateMapOf<String, Boolean>() }
    val everOpened = remember { mutableStateMapOf<String, Boolean>() }
    val loadedCats = remember { mutableStateMapOf<String, Boolean>() }
    val doneCount = remember { mutableStateMapOf<String, Int>() }
    val settled = remember { mutableMapOf<String, MutableSet<Int>>() }

    fun toggle(cat: String) {
        val open = expanded[cat] == true
        expanded[cat] = !open
        if (!open) everOpened[cat] = true
    }

    fun onImgSettled(cat: String, id: Int, total: Int) {
        val set = settled.getOrPut(cat) { mutableSetOf() }
        if (set.add(id)) {
            val d = (doneCount[cat] ?: 0) + 1
            doneCount[cat] = d
            if (d >= total) loadedCats[cat] = true
        }
    }

    fun enterGroceryMode() {
        pendingSelection = vm.groceryList.keys
        groceryMode = true
    }

    BoxWithConstraints(Modifier.fillMaxSize()) {
    val maxPanelHeight = maxHeight / 2
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (groceryMode) {
                Text("${pendingSelection.size} selected", fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
                TextButton(onClick = { vm.setGrocerySelection(pendingSelection); groceryMode = false }) { Text("Done") }
                TextButton(onClick = { groceryMode = false }) { Text("Cancel") }
            } else {
                Text("🔍", fontSize = 14.sp)
                Slider(
                    value = zoom,
                    onValueChange = { zoom = it },
                    onValueChangeFinished = { Prefs.foodZoomPct = (zoom * 100).roundToInt() },
                    valueRange = 0f..1f,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { enterGroceryMode() }) { Text("🛒 Grocery") }
                TextButton(onClick = { editing = Editing.New }) { Text("+ Add") }
            }
        }

        vm.error?.let {
            Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp))
        }

        if (data == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            return@Column
        }

        if (!groceryMode && vm.groceryList.isNotEmpty()) {
            // Capped to half the screen and independently scrollable -- a
            // long shopping list must never crowd out (or trap the user
            // inside) the dish grid below it.
            Box(Modifier.heightIn(max = maxPanelHeight).verticalScroll(rememberScrollState())) {
                GroceryPanel(
                    dishes = data.dishes,
                    list = vm.groceryList,
                    checked = vm.checkedIngredients,
                    onQtyChange = vm::setGroceryQty,
                    onRemove = vm::removeFromGrocery,
                    onEdit = { enterGroceryMode() },
                    onClear = vm::clearGroceryList,
                    onToggleChecked = vm::toggleChecked,
                )
            }
        }

        val extra = if (data.dishes.any { it.category.isBlank() }) listOf("Uncategorised") else emptyList()
        val groups = (data.categories + extra).filter { cat ->
            data.dishes.any { (it.category.ifBlank { "Uncategorised" }) == cat }
        }

        LazyVerticalGrid(
            columns = GridCells.Fixed(columns),
            modifier = Modifier.fillMaxWidth().weight(1f),
            contentPadding = PaddingValues(12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (groups.isEmpty()) {
                item(span = { GridItemSpan(maxLineSpan) }) {
                    Text("No dishes yet — add your first one.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(4.dp))
                }
            }

            groups.forEach { cat ->
                val dishes = data.dishes
                    .filter { (it.category.ifBlank { "Uncategorised" }) == cat }
                    .sortedByDescending { it.rating }
                val isOpen = expanded[cat] == true
                val total = dishes.count { it.image.isNotBlank() }
                val loaded = loadedCats[cat] == true || total == 0
                val done = doneCount[cat] ?: 0

                item(span = { GridItemSpan(maxLineSpan) }, key = "h-$cat") {
                    CategoryHeader(cat, dishes.size, isOpen) { toggle(cat) }
                }

                if (everOpened[cat] == true && isOpen) {
                    if (!loaded) {
                        item(span = { GridItemSpan(maxLineSpan) }, key = "p-$cat") {
                            LoadingBar(done, total)
                        }
                    }
                    gridItems(dishes, key = { it.id }) { dish ->
                        DishCard(
                            dish = dish,
                            armed = confirmDeleteId == dish.id,
                            onEdit = { editing = Editing.Existing(dish) },
                            onArm = { confirmDeleteId = dish.id },
                            onCancelArm = { confirmDeleteId = null },
                            onDelete = {
                                confirmDeleteId = null
                                vm.deleteDish(dish.id)
                            },
                            onImgSettled = { onImgSettled(cat, dish.id, total) },
                            onEditInstructions = { editingInstructions = dish },
                            onEditIngredients = { editingIngredients = dish },
                            groceryMode = groceryMode,
                            selected = dish.id in pendingSelection,
                            onToggleSelect = {
                                pendingSelection =
                                    if (dish.id in pendingSelection) pendingSelection - dish.id
                                    else pendingSelection + dish.id
                            },
                        )
                    }
                }
            }
        }
    }
    }

    when (val e = editing) {
        null -> Unit
        is Editing.New -> DishEditorSheet(
            initial = null,
            categories = data?.categories ?: emptyList(),
            onDismiss = { editing = null },
            onSubmit = { body, _ -> vm.addDish(body); editing = null },
            searchImages = vm::searchImages,
        )
        is Editing.Existing -> DishEditorSheet(
            initial = e.dish,
            categories = data?.categories ?: emptyList(),
            onDismiss = { editing = null },
            onSubmit = { _, patch -> vm.patchDish(e.dish.id, patch); editing = null },
            searchImages = vm::searchImages,
        )
    }

    editingInstructions?.let { d ->
        InstructionsEditorSheet(
            dish = d,
            onDismiss = { editingInstructions = null },
            onSave = { text -> vm.patchDish(d.id, DishPatch(instructions = text)); editingInstructions = null },
            onEditIngredients = { editingInstructions = null; editingIngredients = d },
        )
    }

    editingIngredients?.let { d ->
        IngredientsEditorSheet(
            dish = d,
            onDismiss = { editingIngredients = null },
            onSave = { payload -> vm.patchDish(d.id, DishPatch(ingredients = payload)); editingIngredients = null },
        )
    }
}

@Composable
private fun CategoryHeader(name: String, count: Int, open: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            if (open) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text("  $name  ($count)", fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun LoadingBar(done: Int, total: Int) {
    Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text("Loading images… $done/$total", fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        LinearProgressIndicator(
            progress = { if (total == 0) 0f else done.toFloat() / total },
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        )
    }
}

// ── grocery list ─────────────────────────────────────────────────────────
@Composable
private fun QuantityStepper(value: Int, unit: String?, onChange: (Int) -> Unit, min: Int = 1) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { onChange(maxOf(min, value - 1)) }, enabled = value > min, modifier = Modifier.size(28.dp)) {
            Text("−", fontSize = 16.sp)
        }
        Text(value.toString() + (unit?.takeIf { it.isNotBlank() }?.let { " $it" } ?: ""),
            fontSize = 13.sp, modifier = Modifier.padding(horizontal = 4.dp))
        IconButton(onClick = { onChange(value + 1) }, modifier = Modifier.size(28.dp)) {
            Text("+", fontSize = 16.sp)
        }
    }
}

/** The persistent grocery list -- shown above the dish groups whenever it has
 *  anything in it: one row per selected dish with a quantity picker, then the
 *  combined shopping list below. Mirrors FoodPanel.tsx's GroceryPanel. */
@Composable
private fun GroceryPanel(
    dishes: List<Dish>,
    list: Map<Int, Int>,
    checked: Set<String>,
    onQtyChange: (Int, Int) -> Unit,
    onRemove: (Int) -> Unit,
    onEdit: () -> Unit,
    onClear: () -> Unit,
    onToggleChecked: (String) -> Unit,
) {
    val byId = dishes.associateBy { it.id }
    val entries = list.entries.mapNotNull { (id, qty) -> byId[id]?.let { it to qty } }
    if (entries.isEmpty()) return
    val totals = remember(dishes, list) { computeGroceryTotals(dishes, list) }

    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(10.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("🛒 Grocery list", fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.weight(1f))
            TextButton(onClick = onEdit) { Text("Edit") }
            TextButton(onClick = onClear) { Text("Clear", color = MaterialTheme.colorScheme.primary) }
        }
        entries.forEach { (dish, qty) ->
            val unit = parseIngredients(dish.ingredients).unit
            Row(
                Modifier.fillMaxWidth().padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(dish.name, fontSize = 13.sp, modifier = Modifier.weight(1f),
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                QuantityStepper(value = qty, unit = unit, onChange = { onQtyChange(dish.id, it) })
                IconButton(onClick = { onRemove(dish.id) }, modifier = Modifier.size(28.dp)) {
                    Icon(Icons.Default.Delete, "Remove", tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(16.dp))
                }
            }
        }
        if (totals.isNotEmpty()) {
            Text("Shopping list", fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                modifier = Modifier.padding(top = 8.dp, bottom = 2.dp))
            totals.forEach { t ->
                val isChecked = t.key in checked
                val lineColor = if (isChecked) MaterialTheme.colorScheme.onSurfaceVariant else Color.Unspecified
                val decoration = if (isChecked) TextDecoration.LineThrough else TextDecoration.None
                Row(
                    Modifier.fillMaxWidth().clickable { onToggleChecked(t.key) }.padding(vertical = 3.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = isChecked, onCheckedChange = { onToggleChecked(t.key) },
                        modifier = Modifier.size(28.dp))
                    Text(t.name, fontSize = 13.sp, modifier = Modifier.weight(1f),
                        color = lineColor, textDecoration = decoration)
                    if (t.amount != null) {
                        Text(
                            formatAmount(t.amount) + (t.unit.takeIf { it.isNotBlank() }?.let { " $it" } ?: "") +
                                (if (t.approximate) "+" else ""),
                            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textDecoration = decoration,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DishCard(
    dish: Dish,
    armed: Boolean,
    onEdit: () -> Unit,
    onArm: () -> Unit,
    onCancelArm: () -> Unit,
    onDelete: () -> Unit,
    onImgSettled: () -> Unit,
    onEditInstructions: () -> Unit,
    onEditIngredients: () -> Unit,
    groceryMode: Boolean,
    selected: Boolean,
    onToggleSelect: () -> Unit,
) {
    val context = LocalContext.current
    val processed = dish.instructions.isNotBlank() || dish.ingredients.isNotBlank()
    val eligibleForGrocery = dish.ingredients.isNotBlank()

    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surface)
            .let { if (groceryMode) it.clickable(enabled = eligibleForGrocery, onClick = onToggleSelect) else it },
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(4f / 3f)
                .background(MaterialTheme.colorScheme.surfaceVariant)
                // Tapping the image opens ingredients -- the single most
                // reached-for action -- mirroring FoodPanel.tsx's
                // dish-card-img button; grocery mode already makes the
                // whole card the selection toggle, so this only applies
                // to the normal browsing mode.
                .let { if (!groceryMode) it.clickable(onClick = onEditIngredients) else it },
            contentAlignment = Alignment.Center,
        ) {
            if (dish.image.isNotBlank()) {
                AsyncImage(
                    model = ImageRequest.Builder(context)
                        .data(Api.dishImageUrl(dish.image))
                        .crossfade(true)
                        .build(),
                    imageLoader = FoodImages.loader(context),
                    contentDescription = dish.name,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                    onSuccess = { onImgSettled() },
                    onError = { onImgSettled() },
                )
            } else {
                Text("🍽", fontSize = 26.sp)
            }
            if (groceryMode) {
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(4.dp)
                        .size(22.dp)
                        .clip(CircleShape)
                        .background(if (selected) MaterialTheme.colorScheme.primary else Color(0x88000000)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(if (selected) "✓" else "", color = Color.White, fontSize = 13.sp)
                }
                if (!eligibleForGrocery) {
                    Box(Modifier.fillMaxSize().background(Color(0x99000000)), contentAlignment = Alignment.Center) {
                        Text("No ingredients", color = Color.White, fontSize = 10.sp)
                    }
                }
            }
        }

        if (groceryMode) {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 40.dp).padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(dish.name, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(ratingShort(dish.rating), color = Gold, fontSize = 11.sp, maxLines = 1)
                }
            }
        } else if (armed) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                TextButton(
                    onClick = onDelete,
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                ) { Text("Delete", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp) }
                TextButton(
                    onClick = onCancelArm,
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                ) { Text("Cancel", fontSize = 12.sp) }
            }
        } else {
            // Name gets its own full-width line; rating and every action
            // icon share the line below it, packed to the right.
            Column(Modifier.fillMaxWidth().padding(start = 8.dp, end = 2.dp, top = 2.dp)) {
                Text(dish.name, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 32.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(ratingShort(dish.rating), color = Gold, fontSize = 11.sp, maxLines = 1)
                    Spacer(Modifier.weight(1f))
                    if (dish.url.isNotBlank() && !processed) {
                        Box(
                            Modifier.size(8.dp).clip(CircleShape)
                                .background(if (dish.has_text) Color(0xFF46A758) else Color(0xFFE5484D)),
                        )
                        Spacer(Modifier.width(4.dp))
                    }
                    IconButton(onClick = onEditInstructions, modifier = Modifier.size(28.dp)) {
                        Text("📄", fontSize = 13.sp)
                    }
                    if (dish.url.isNotBlank()) {
                        IconButton(
                            onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(dish.url))) },
                            modifier = Modifier.size(28.dp),
                        ) {
                            Icon(Icons.Default.OpenInNew, "Open recipe", modifier = Modifier.size(14.dp))
                        }
                    }
                    IconButton(onClick = onEdit, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Default.Edit, "Edit", modifier = Modifier.size(15.dp))
                    }
                    IconButton(onClick = onArm, modifier = Modifier.size(28.dp)) {
                        Icon(Icons.Default.Delete, "Delete",
                            tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(15.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun InstructionsEditorSheet(
    dish: Dish,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
    onEditIngredients: () -> Unit,
) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    // Nothing to look at yet -> go straight to editing; otherwise show the
    // saved text first, with an explicit Edit step.
    var editMode by remember { mutableStateOf(dish.instructions.isBlank()) }
    var text by remember { mutableStateOf(dish.instructions) }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier.fillMaxWidth().fillMaxHeight(0.85f)
                .padding(horizontal = 16.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("${dish.name} — Instructions", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            if (editMode) {
                OutlinedTextField(
                    value = text, onValueChange = { text = it },
                    placeholder = { Text("Write the steps…") },
                    modifier = Modifier.fillMaxWidth().weight(1f),
                )
            } else {
                Text(
                    dish.instructions, fontSize = 13.sp,
                    modifier = Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (editMode) {
                    Button(onClick = { onSave(text) }) { Text("Save") }
                    TextButton(onClick = {
                        text = dish.instructions
                        if (dish.instructions.isNotBlank()) editMode = false else onDismiss()
                    }) { Text("Cancel") }
                } else {
                    Button(onClick = { editMode = true }) { Text("Edit") }
                    TextButton(onClick = onEditIngredients) { Text("Ingredients") }
                    TextButton(onClick = onDismiss) { Text("Close") }
                }
            }
        }
    }
}

private val LOWER_WORD_RE = Regex("^[a-z]+( [a-z]+)*$")
private val PLAIN_NUMBER_RE = Regex("^\\d+(\\.\\d+)?$")

private data class IngredientRow(val name: String, val quantity: String, val unit: String)

/** Same shape rules as the backend's _validate_ingredients_json, applied
 *  per-field since the editor keeps quantity/unit apart. null = valid. */
private fun IngredientRow.error(): String? {
    val n = name.trim(); val q = quantity.trim(); val u = unit.trim()
    if (n.isNotEmpty() && !LOWER_WORD_RE.matches(n)) return "name must be lowercase letters only"
    if (q.isNotEmpty() && !PLAIN_NUMBER_RE.matches(q)) return "quantity must be a number, or left blank"
    if (u.isNotEmpty() && !LOWER_WORD_RE.matches(u)) return "unit must be lowercase letters only"
    if (u.isNotEmpty() && q.isEmpty()) return "a unit needs a quantity"
    return null
}

private val ingredientsJson = Json { ignoreUnknownKeys = true }

@Composable
private fun IngredientsEditorSheet(
    dish: Dish,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val initial = remember(dish.ingredients) { parseIngredients(dish.ingredients) }
    var quantity by remember { mutableStateOf(initial.quantity) }
    var unit by remember { mutableStateOf(initial.unit) }
    var rows by remember {
        mutableStateOf(initial.ingredients.map { (n, e) -> IngredientRow(n, e.quantity, e.unit) })
    }
    var error by remember { mutableStateOf<String?>(null) }

    fun save() {
        val bad = rows.any { it.name.trim().isNotEmpty() && it.error() != null }
        if (bad) {
            error = "Fix the highlighted ingredient(s) before saving."
            return
        }
        val map = rows.mapNotNull { r ->
            val name = r.name.trim()
            if (name.isEmpty()) null else name to IngredientEntry(r.quantity.trim(), r.unit.trim())
        }.toMap()
        // No rows left -> clear the field entirely (an empty {} would fail
        // the backend's "non-empty object" check, and isn't what "cleared" means).
        val payload = if (map.isEmpty()) "" else
            ingredientsJson.encodeToString(IngredientsData.serializer(), IngredientsData(quantity.trim(), unit.trim(), map))
        onSave(payload)
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier.fillMaxWidth().fillMaxHeight(0.9f)
                .padding(horizontal = 16.dp).padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("${dish.name} — Ingredients", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = quantity, onValueChange = { quantity = it },
                    label = { Text("Quantity") }, placeholder = { Text("e.g. 4") },
                    singleLine = true, modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = unit, onValueChange = { unit = it.lowercase() },
                    label = { Text("Unit") }, placeholder = { Text("e.g. persons") },
                    singleLine = true, modifier = Modifier.weight(1f),
                )
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                rows.forEachIndexed { i, r ->
                    val err = if (r.name.trim().isNotEmpty()) r.error() else null
                    Column(Modifier.padding(vertical = 3.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            OutlinedTextField(
                                value = r.name, onValueChange = { v -> rows = rows.toMutableList().also { it[i] = r.copy(name = v.lowercase()) } },
                                placeholder = { Text("name") }, singleLine = true,
                                isError = err != null, modifier = Modifier.weight(2f),
                            )
                            OutlinedTextField(
                                value = r.quantity, onValueChange = { v -> rows = rows.toMutableList().also { it[i] = r.copy(quantity = v) } },
                                placeholder = { Text("qty") }, singleLine = true,
                                isError = err != null, modifier = Modifier.weight(1f),
                            )
                            OutlinedTextField(
                                value = r.unit, onValueChange = { v -> rows = rows.toMutableList().also { it[i] = r.copy(unit = v.lowercase()) } },
                                placeholder = { Text("unit") }, singleLine = true,
                                isError = err != null, modifier = Modifier.weight(1f),
                            )
                            IconButton(onClick = { rows = rows.toMutableList().also { it.removeAt(i) } }, modifier = Modifier.size(28.dp)) {
                                Icon(Icons.Default.Delete, "Remove", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp))
                            }
                        }
                        err?.let { Text(it, fontSize = 11.sp, color = MaterialTheme.colorScheme.primary) }
                    }
                }
                TextButton(onClick = { rows = rows + IngredientRow("", "", "") }) { Text("+ Add ingredient") }
            }
            error?.let { Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp) }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = { save() }) { Text("Save") }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        }
    }
}

@Composable
private fun DishEditorSheet(
    initial: Dish?,
    categories: List<String>,
    onDismiss: () -> Unit,
    onSubmit: (DishBody, DishPatch) -> Unit,
    searchImages: (String, (List<ImageHit>) -> Unit, (String) -> Unit) -> Unit,
) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var name by remember { mutableStateOf(initial?.name ?: "") }
    var category by remember { mutableStateOf(initial?.category ?: "") }
    var rating by remember { mutableStateOf((initial?.rating ?: 7).toFloat()) }
    var recipeUrl by remember { mutableStateOf(initial?.url ?: "") }
    // null = keep current image; non-null = newly picked URL to download.
    var pickedUrl by remember { mutableStateOf<String?>(null) }
    var picking by remember { mutableStateOf(false) }
    val context = LocalContext.current

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(if (initial == null) "New dish" else "Edit dish",
                fontWeight = FontWeight.SemiBold, fontSize = 16.sp)

            OutlinedTextField(
                value = name, onValueChange = { name = it },
                label = { Text("Name") }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            OutlinedTextField(
                value = category, onValueChange = { category = it },
                label = { Text("Category") }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            if (categories.isNotEmpty()) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    categories.forEach { c ->
                        FilterChip(
                            selected = category == c,
                            onClick = { category = c },
                            label = { Text(c) },
                        )
                    }
                }
            }

            OutlinedTextField(
                value = recipeUrl, onValueChange = { recipeUrl = it },
                label = { Text("Recipe URL") }, placeholder = { Text("https://…") }, singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            Text("Rating: ${rating.roundToInt()}   ${stars(rating.roundToInt())}",
                fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Slider(
                value = rating, onValueChange = { rating = it },
                valueRange = 0f..10f, steps = 9,
            )

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val preview = pickedUrl ?: initial?.image?.takeIf { it.isNotBlank() }
                    ?.let { Api.dishImageUrl(it) }
                Box(
                    Modifier
                        .size(width = 120.dp, height = 90.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant),
                    contentAlignment = Alignment.Center,
                ) {
                    if (preview != null) {
                        AsyncImage(
                            model = ImageRequest.Builder(context).data(preview).crossfade(true).build(),
                            imageLoader = FoodImages.loader(context),
                            contentDescription = null,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.fillMaxSize(),
                        )
                    } else {
                        Text("🍽", fontSize = 24.sp)
                    }
                }
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Button(onClick = { picking = true }) {
                        Text(if (pickedUrl != null || initial?.image?.isNotBlank() == true) "Change image…" else "Pick image…")
                    }
                    if (pickedUrl != null) {
                        TextButton(onClick = { pickedUrl = null }) { Text("Reset") }
                    }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(
                    onClick = {
                        val r = rating.roundToInt()
                        if (initial == null) {
                            onSubmit(
                                DishBody(name.trim(), category.trim(), r, pickedUrl, recipeUrl.trim()),
                                DishPatch(),
                            )
                        } else {
                            onSubmit(
                                DishBody(name.trim(), category.trim(), r, pickedUrl, recipeUrl.trim()),
                                DishPatch(
                                    name = name.trim().ifBlank { null },
                                    category = category.trim(),
                                    rating = r,
                                    image_url = pickedUrl,
                                    url = recipeUrl.trim(),
                                ),
                            )
                        }
                    },
                    enabled = name.isNotBlank(),
                ) { Text(if (initial == null) "Create" else "Save") }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        }
    }

    if (picking) {
        ImagePickerSheet(
            initialQuery = name.trim().ifBlank { category.trim() },
            searchImages = searchImages,
            onPick = { pickedUrl = it; picking = false },
            onDismiss = { picking = false },
        )
    }
}

@Composable
private fun ImagePickerSheet(
    initialQuery: String,
    searchImages: (String, (List<ImageHit>) -> Unit, (String) -> Unit) -> Unit,
    onPick: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val context = LocalContext.current
    var query by remember { mutableStateOf(initialQuery) }
    var results by remember { mutableStateOf<List<ImageHit>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var searched by remember { mutableStateOf(false) }

    fun run() {
        if (query.isBlank()) return
        loading = true; error = null; searched = true
        searchImages(query.trim(), { results = it; loading = false }, { error = it; loading = false })
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier.fillMaxWidth().fillMaxHeight(0.92f).padding(horizontal = 16.dp).padding(bottom = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = query, onValueChange = { query = it },
                    label = { Text("Search images") }, singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Button(onClick = { run() }) { Text("Search") }
            }
            if (loading) {
                Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
            error?.let {
                Text(it, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
            }
            if (!searched && !loading) {
                Text("Type a search term and tap Search.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
            LazyVerticalGrid(
                columns = GridCells.Adaptive(minSize = 150.dp),
                modifier = Modifier.fillMaxWidth().weight(1f),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                gridItems(results, key = { it.url }) { hit ->
                    AsyncImage(
                        model = ImageRequest.Builder(context)
                            .data(hit.thumbnail.ifBlank { hit.url })
                            .crossfade(true)
                            .build(),
                        imageLoader = FoodImages.loader(context),
                        contentDescription = hit.title,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .aspectRatio(1f)
                            .clip(RoundedCornerShape(8.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant)
                            .clickable { onPick(hit.url) },
                    )
                }
            }
        }
    }
}
