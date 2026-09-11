@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.diary.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.Button
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
import kotlin.math.roundToInt

/** Card width at the min-zoom end — sets how many columns you can fan out to. */
private const val MIN_CARD_DP = 120
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

private sealed interface Editing {
    data object New : Editing
    data class Existing(val dish: Dish) : Editing
}

@Composable
fun FoodScreen(vm: FoodViewModel = viewModel()) {
    val data = vm.data
    var editing by remember { mutableStateOf<Editing?>(null) }
    var confirmDeleteId by remember { mutableStateOf<Int?>(null) }
    // 0f = min zoom (many small columns) … 1f = max zoom (1–2 columns).
    var zoom by remember { mutableStateOf((Prefs.foodZoomPct.coerceIn(0, 100)) / 100f) }

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

    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("🔍", fontSize = 14.sp)
            Slider(
                value = zoom,
                onValueChange = { zoom = it },
                onValueChangeFinished = { Prefs.foodZoomPct = (zoom * 100).roundToInt() },
                valueRange = 0f..1f,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = { editing = Editing.New }) { Text("+ Add") }
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

        val extra = if (data.dishes.any { it.category.isBlank() }) listOf("Uncategorised") else emptyList()
        val groups = (data.categories + extra).filter { cat ->
            data.dishes.any { (it.category.ifBlank { "Uncategorised" }) == cat }
        }

        LazyVerticalGrid(
            columns = GridCells.Fixed(columns),
            modifier = Modifier.fillMaxSize(),
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
                        )
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

@Composable
private fun DishCard(
    dish: Dish,
    armed: Boolean,
    onEdit: () -> Unit,
    onArm: () -> Unit,
    onCancelArm: () -> Unit,
    onDelete: () -> Unit,
    onImgSettled: () -> Unit,
) {
    val context = LocalContext.current
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surface),
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(4f / 3f)
                .background(MaterialTheme.colorScheme.surfaceVariant),
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
        }

        if (armed) {
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
            Row(
                Modifier.fillMaxWidth().heightIn(min = 40.dp).padding(start = 8.dp, end = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(dish.name, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(ratingShort(dish.rating), color = Gold, fontSize = 11.sp, maxLines = 1)
                }
                IconButton(onClick = onEdit, modifier = Modifier.size(34.dp)) {
                    Icon(Icons.Default.Edit, "Edit", modifier = Modifier.size(18.dp))
                }
                IconButton(onClick = onArm, modifier = Modifier.size(34.dp)) {
                    Icon(Icons.Default.Delete, "Delete",
                        tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                }
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
    // null = keep current image; non-null = newly picked URL to download.
    var pickedUrl by remember { mutableStateOf<String?>(null) }
    var picking by remember { mutableStateOf(false) }
    val context = LocalContext.current

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet) {
        Column(
            Modifier
                .fillMaxWidth()
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
                                DishBody(name.trim(), category.trim(), r, pickedUrl),
                                DishPatch(),
                            )
                        } else {
                            onSubmit(
                                DishBody(name.trim(), category.trim(), r, pickedUrl),
                                DishPatch(
                                    name = name.trim().ifBlank { null },
                                    category = category.trim(),
                                    rating = r,
                                    image_url = pickedUrl,
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
