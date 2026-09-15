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
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.github.mikephil.charting.charts.BarChart
import com.github.mikephil.charting.components.Legend
import com.github.mikephil.charting.components.XAxis
import com.github.mikephil.charting.data.BarData
import com.github.mikephil.charting.data.BarDataSet
import com.github.mikephil.charting.data.BarEntry
import com.github.mikephil.charting.data.Entry
import com.github.mikephil.charting.formatter.IndexAxisValueFormatter
import com.github.mikephil.charting.highlight.Highlight
import com.github.mikephil.charting.interfaces.datasets.IBarDataSet
import com.github.mikephil.charting.listener.OnChartValueSelectedListener

/** Hourly bar chart with the same look + tap-readout as [LineChart]. One dataset
 *  draws plain bars; several draw grouped bars (used only when more than one city
 *  is selected). */
@Composable
fun BarChart(
    title: String,
    xLabels: List<String>,
    series: List<ChartSeries>,
    modifier: Modifier = Modifier,
    pointLabels: List<String> = xLabels,
) {
    val axis = MaterialTheme.colorScheme.onSurfaceVariant.toArgb()
    val grid = MaterialTheme.colorScheme.outline.toArgb()
    var readout by remember { mutableStateOf<String?>(null) }
    val tapLabels = rememberUpdatedState(pointLabels)
    val axisLabels = rememberUpdatedState(xLabels)
    val nSets = rememberUpdatedState(series.size)
    // group width — computed in `update`, read by the (once-built) tap listener
    // to map a fractional x back to an hour index.
    var groupW by remember { mutableStateOf(1f) }

    Column(modifier.padding(top = 8.dp)) {
        Text(
            text = title,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.padding(start = 4.dp),
        )
        Text(
            text = readout ?: " ",
            fontSize = 11.sp,
            maxLines = 1,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(start = 4.dp, bottom = 2.dp),
        )
        AndroidView(
            modifier = Modifier.fillMaxWidth().height(220.dp),
            factory = { ctx ->
                BarChart(ctx).apply {
                    description.isEnabled = false
                    setNoDataText("no data")
                    setNoDataTextColor(axis)
                    setTouchEnabled(true)
                    isDragEnabled = true
                    setScaleEnabled(true)
                    setPinchZoom(true)
                    setDrawGridBackground(false)
                    setFitBars(true)
                    legend.apply {
                        textColor = axis
                        isWordWrapEnabled = true
                        verticalAlignment = Legend.LegendVerticalAlignment.TOP
                        horizontalAlignment = Legend.LegendHorizontalAlignment.LEFT
                        isEnabled = false
                    }
                    axisRight.isEnabled = false
                    axisLeft.apply {
                        textColor = axis
                        gridColor = grid
                        setDrawAxisLine(false)
                        axisMinimum = 0f
                    }
                    xAxis.apply {
                        textColor = axis
                        gridColor = grid
                        position = XAxis.XAxisPosition.BOTTOM
                        setDrawGridLines(false)
                        setDrawAxisLine(false)
                        setLabelCount(6, false)
                        granularity = 1f
                    }
                    setOnChartValueSelectedListener(object : OnChartValueSelectedListener {
                        override fun onValueSelected(e: Entry?, h: Highlight?) {
                            if (e == null) return
                            val i = if (nSets.value > 1) (e.x / groupW).toInt() else e.x.toInt()
                            val label = tapLabels.value.getOrNull(i)
                                ?: axisLabels.value.getOrNull(i) ?: i.toString()
                            val name = data?.getDataSetByIndex(h?.dataSetIndex ?: 0)?.label ?: ""
                            readout = "$label · $name  ${"%.2f".format(e.y)}"
                        }
                        override fun onNothingSelected() { readout = null }
                    })
                }
            },
            update = { chart ->
                val n = series.size
                val sets: List<IBarDataSet> = series.mapIndexed { si, s ->
                    val entries = s.points.mapIndexedNotNull { i, v -> v?.let { BarEntry(i.toFloat(), it) } }
                    BarDataSet(entries, s.name).apply {
                        color = s.color.toArgb()
                        setDrawValues(false)
                        highLightColor = s.color.toArgb()
                        highLightAlpha = 90
                    }
                }
                val barData = BarData(sets)
                chart.legend.isEnabled = n > 1
                chart.xAxis.valueFormatter = IndexAxisValueFormatter(xLabels)

                if (n > 1) {
                    val groupSpace = 0.30f
                    val barSpace = 0.02f
                    barData.barWidth = (1f - groupSpace) / n - barSpace
                    chart.data = barData
                    val gw = barData.getGroupWidth(groupSpace, barSpace)
                    groupW = gw
                    chart.xAxis.setCenterAxisLabels(true)
                    chart.xAxis.axisMinimum = 0f
                    chart.xAxis.axisMaximum = gw * xLabels.size
                    chart.groupBars(0f, groupSpace, barSpace)
                } else {
                    barData.barWidth = 0.85f
                    chart.data = barData
                    groupW = 1f
                    chart.xAxis.setCenterAxisLabels(false)
                    chart.xAxis.axisMinimum = -0.5f
                    chart.xAxis.axisMaximum = xLabels.size - 0.5f
                }
                chart.invalidate()
            },
        )
    }
}
