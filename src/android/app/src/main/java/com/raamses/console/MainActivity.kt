package com.raamses.console

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.raamses.console.ui.navigation.RaamsesNavHost
import com.raamses.console.ui.theme.RaamsesTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as RaamsesApp

        setContent {
            RaamsesTheme {
                RaamsesNavHost(
                    mockProvider = app.mockProvider
                )
            }
        }
    }
}
