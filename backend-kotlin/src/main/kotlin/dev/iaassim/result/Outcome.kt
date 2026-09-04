package dev.iaassim.result

sealed interface Outcome<out T, out E>

data class Ok<out T>(val value: T) : Outcome<T, Nothing>

data class Err<out E>(val error: E) : Outcome<Nothing, E>
