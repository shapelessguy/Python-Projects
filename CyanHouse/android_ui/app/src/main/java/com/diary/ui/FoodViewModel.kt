package com.diary.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.diary.net.Api
import com.diary.net.DishBody
import com.diary.net.DishPatch
import com.diary.net.FoodData
import com.diary.net.ImageHit
import com.diary.net.versionPoll
import kotlinx.coroutines.launch

/** Food catalogue state. Same load / version-poll-guard / snapshot-reply
 *  pattern as [PersonalViewModel] — a change from another client bumps
 *  `food` in the version poll and triggers a refetch. */
class FoodViewModel : ViewModel() {
    var data by mutableStateOf<FoodData?>(null); private set
    var error by mutableStateOf<String?>(null); private set

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
}
