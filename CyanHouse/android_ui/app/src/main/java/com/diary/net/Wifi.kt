package com.diary.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/** Whether any connected network is Wi-Fi -- checked across all networks, not
 *  just the active one, so a VPN or a mobile-data-preferred setup on top of a
 *  live Wi-Fi link still counts. Needs ACCESS_NETWORK_STATE. */
@Suppress("DEPRECATION")
fun isOnWifi(context: Context): Boolean {
    val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
    return cm.allNetworks.any { cm.getNetworkCapabilities(it)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true }
}
