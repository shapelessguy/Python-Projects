package com.diary.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.github.mikephil.charting.charts.LineChart
import com.github.mikephil.charting.components.Legend
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.data.LineData
import com.github.mikephil.charting.data.LineDataSet
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.github.mikephil.charting.highlight.Highlight
import com.github.mikephil.charting.interfaces.datasets.ILineDataSet
import com.github.mikephil.charting.listener.OnChartValueSelectedListener

data class ChartSeries(val name: String, val color: Color, val points: List<Float?>)

/** Pinch-zoom, drag, and tap-a-point-for-its-value. Legend lists the series. */
@Composable
fun LineChart(
    title: String,
    xLabels: List<String>,
    series: List<ChartSeries>,
    modifier: Modifier = Modifier,
    /** Label shown when a point is tapped; defaults to the axis label. Lets the
     *  caller give a richer readout (day+hour, a week's date range) than the
     *  compact axis tick. */
    pointLabels: List<String> = xLabels,
    /** Fix the left-axis range (e.g. 0f..100f for a percentage). Null = autoscale. */
    yMin: Float? = null,
    yMax: Float? = null,
) {
    val axis = MaterialTheme.colorScheme.onSurfaceVariant.toArgb()
    val grid = MaterialTheme.colorScheme.outline.toArgb()
    var readout by remember { mutableStateOf<String?>(null) }
    // The chart View (and its tap listener) is built once in `factory`; these
    // keep the listener reading the current labels after a resample change.
    val axisLabels = rememberUpdatedState(xLabels)
    val tapLabels = rememberUpdatedState(pointLabels)

    Column(modifier.padding(top = 8.dp)) {
        Text(
            text = title,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.padding(start = 4.dp),
        )
        Text(
            text = readout ?: " ",  // reserve the line so the chart doesn't jump
            fontSize = 11.sp,
            maxLines = 1,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(start = 4.dp, bottom = 2.dp),
        )
        AndroidView(
            modifier = Modifier.fillMaxWidth().height(240.dp),
            factory = { ctx ->
                LineChart(ctx).apply {
                    description.isEnabled = false
                    setNoDataText("no data")
                    setNoDataTextColor(axis)
                    setTouchEnabled(true)
                    isDragEnabled = true
                    setScaleEnabled(true)
                    setPinchZoom(true)
                    setDrawGridBackground(false)
                    legend.apply {
                        textColor = axis
                        isWordWrapEnabled = true
                        verticalAlignment = Legend.LegendVerticalAlignment.TOP
                        horizontalAlignment = Legend.LegendHorizontalAlignment.LEFT
                    }
                    axisRight.isEnabled = false
                    axisLeft.apply {
                        textColor = axis
                        gridColor = grid
                        setDrawAxisLine(false)
                    }
                    xAxis.apply {
                        textColor = axis
                        gridColor = grid
                        position = XAxis.XAxisPosition.BOTTOM
                        setDrawGridLines(false)
                        setDrawAxisLine(false)
                        setLabelCount(4, false)
                        granularity = 1f
                    }
                    setOnChartValueSelectedListener(object : OnChartValueSelectedListener {
                        override fun onValueSelected(e: Entry?, h: Highlight?) {
                            if (e == null) return
                            val i = e.x.toInt()
                            val label = tapLabels.value.getOrNull(i)
                                ?: axisLabels.value.getOrNull(i)
                                ?: i.toString()
                            val name = data?.getDataSetByIndex(h?.dataSetIndex ?: 0)?.label ?: ""
                            readout = "$label · $name  ${"%.2f".format(e.y)}"
                        }
                        override fun onNothingSelected() { readout = null }
                    })
                }
            },
            update = { chart ->
                val sets: List<ILineDataSet> = series.map { s ->
                    val entries = s.points.mapIndexedNotNull { i, v -> v?.let { Entry(i.toFloat(), it) } }
                    LineDataSet(entries, s.name).apply {
                        color = s.color.toArgb()
                        lineWidth = 1.8f
                        setDrawCircles(false)
                        setDrawValues(false)
                        setDrawHighlightIndicators(true)
                        highLightColor = s.color.toArgb()
                        mode = LineDataSet.Mode.LINEAR
                    }
                }
                chart.data = LineData(sets)
                chart.xAxis.valueFormatter = IndexAxisValueFormatter(xLabels)
                if (yMin != null) chart.axisLeft.axisMinimum = yMin else chart.axisLeft.resetAxisMinimum()
                if (yMax != null) chart.axisLeft.axisMaximum = yMax else chart.axisLeft.resetAxisMaximum()
                chart.invalidate()
            },
        )
    }
}
