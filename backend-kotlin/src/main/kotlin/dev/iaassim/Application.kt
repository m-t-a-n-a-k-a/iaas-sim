package dev.iaassim

import io.ktor.http.ContentType
import io.ktor.server.application.Application
import io.ktor.server.application.call
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.routing

private const val HEALTH_RESPONSE = "{\"status\":\"ok\"}"

fun Application.module() {
    routing {
        get("/health") {
            call.respondText(HEALTH_RESPONSE, ContentType.Application.Json)
        }
    }
}

fun main() {
    embeddedServer(Netty, host = "0.0.0.0", port = 8080, module = Application::module)
        .start(wait = true)
}
