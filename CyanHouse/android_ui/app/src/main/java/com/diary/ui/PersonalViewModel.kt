package com.diary.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.diary.net.Api
import com.diary.net.ColumnBody
import com.diary.net.ColumnPatch
import com.diary.net.MonthData
import com.diary.net.versionPoll
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import java.time.YearMonth
import java.time.format.TextStyle
import java.util.Locale

class PersonalViewModel : ViewModel() {
    var month by mutableStateOf(YearMonth.now().toString()); private set
    var data by mutableStateOf<MonthData?>(null); private set
    var error by mutableStateOf<String?>(null); private set

    private var appliedVersion = -1
    private var seenDiary = 0

    init {
        load()
        viewModelScope.launch {
            versionPoll().collect { v ->
                // react only to a diary version we have not applied ourselves
                if (v.diary == seenDiary) return@collect
                seenDiary = v.diary
                if (data != null && v.diary != appliedVersion) load()
            }
        }
    }

    val monthLabel: String
        get() = YearMonth.parse(month).let {
            "${it.month.getDisplayName(TextStyle.FULL, Locale.getDefault()).replaceFirstChar(Char::uppercase)} ${it.year}"
        }

    fun prevMonth() = goToMonth(YearMonth.parse(month).minusMonths(1).toString())
    fun nextMonth() = goToMonth(YearMonth.parse(month).plusMonths(1).toString())
    fun currentMonth() = goToMonth(YearMonth.now().toString())
    private fun goToMonth(m: String) { month = m; load() }

    private fun load() = viewModelScope.launch {
        runCatching { Api.month(month) }
            .onSuccess { apply(it) }
            .onFailure { error = it.message }
    }

    private fun apply(d: MonthData) {
        data = d
        appliedVersion = d.version
        error = null
    }

    fun putDay(date: String, values: JsonObject) = viewModelScope.launch {
        runCatching { Api.putDay(date, values) }
            .onSuccess { apply(it) }
            .onFailure { error = it.message }
    }

    fun addColumn(body: ColumnBody) = mutate { Api.addColumn(body, month) }
    fun patchColumn(key: String, patch: ColumnPatch) = mutate { Api.patchColumn(key, patch, month) }
    fun deleteColumn(key: String) = mutate { Api.deleteColumn(key, month) }
    fun addUnit(unit: String) = mutate { Api.addUnit(unit, month) }
    fun deleteUnit(unit: String) = mutate { Api.deleteUnit(unit, month) }

    private fun mutate(block: suspend () -> MonthData) = viewModelScope.launch {
        runCatching { block() }
            .onSuccess { apply(it) }
            .onFailure { error = it.message }
    }
}
