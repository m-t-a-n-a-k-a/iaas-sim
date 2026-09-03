# Expression heterogeneous effect typing spike

The source in `expression_heterogeneous_effect.py.txt` was copied to a `.py`
file and checked with the repository's strict Pyright configuration against
Python 3.14.4 and Expression 5.7.0.

Pyright inferred the generator's yielded type as the union of all five success
types:

```text
Generator[
  BackendVirtualMachineRef
  | ObservedVirtualMachine
  | AcceptedPowerCommand
  | BackendOperationRef
  | Operation,
  Unknown,
  Operation,
]
```

That generator cannot be passed to
`@effect.result[Operation, ApplicationError]()`. The installed builder types
its decorated generator with one `_TSource`, so selecting `Operation` to keep
the final `Result[Operation, ApplicationError]` precise also requires every
yielded success value to be `Operation | None`. Pyright consequently reports
`reportArgumentType` at the decorator and `reportUnknownParameterType` on the
generator function.

Widening `_TSource` to `object` or to the union above would violate the spike's
acceptance criteria and widen the decorated function's final Result. No `Any`,
cast, `type: ignore`, suppression, comprehension, conversion bridge, or custom
builder was used. Production migration therefore stopped at the typing gate.
