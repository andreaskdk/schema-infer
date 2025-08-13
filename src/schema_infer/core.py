from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Sequence, Set, Tuple
from datetime import date, datetime
import math

# ------------------------------
# Schema model
# ------------------------------

class Schema:
    """Base class for schemas."""
    def merge(self, other: "Schema") -> "Schema":
        if self == other:
            return self
        return UnionSchema.of(self, other)

    def to_jsonschema(self) -> Dict[str, Any]:
        """Return a JSON-Schema-like dict (draft-ish) for interop."""
        raise NotImplementedError

    def coerce(self, value: Any) -> Any:
        """Attempt to coerce a value into this schema (best-effort, may raise)."""
        return value  # defaults to identity

@dataclass(frozen=True)
class NullSchema(Schema):
    def __repr__(self): return "Null"
    def to_jsonschema(self): return {"type": "null"}
    def coerce(self, value: Any) -> Any:
        if value is None:
            return None
        raise TypeError("Cannot coerce non-null to null")

@dataclass(frozen=True)
class BoolSchema(Schema):
    def __repr__(self): return "Bool"
    def to_jsonschema(self): return {"type": "boolean"}
    def coerce(self, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "t", "1", "yes", "y"}: return True
            if v in {"false", "f", "0", "no", "n"}: return False
        raise TypeError(f"Cannot coerce {value!r} to bool")

@dataclass(frozen=True)
class IntSchema(Schema):
    def __repr__(self): return "Int"
    def to_jsonschema(self): return {"type": "integer"}
    def coerce(self, value: Any) -> Any:
        if isinstance(value, bool):
            # Avoid bool-as-int surprises
            raise TypeError("Bool is not accepted as Int")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            s = value.strip()
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                return int(s)
        raise TypeError(f"Cannot coerce {value!r} to int")

@dataclass(frozen=True)
class FloatSchema(Schema):
    def __repr__(self): return "Float"
    def to_jsonschema(self): return {"type": "number"}
    def coerce(self, value: Any) -> Any:
        if isinstance(value, bool):
            raise TypeError("Bool is not accepted as Float")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                f = float(value.strip())
                if math.isfinite(f):
                    return f
            except ValueError:
                pass
        raise TypeError(f"Cannot coerce {value!r} to float")

@dataclass(frozen=True)
class StringSchema(Schema):
    def __repr__(self): return "String"
    def to_jsonschema(self): return {"type": "string"}
    def coerce(self, value: Any) -> Any:
        if value is None:
            return None  # passthrough; caller decides if Null allowed
        return str(value)

@dataclass(frozen=True)
class BytesSchema(Schema):
    def __repr__(self): return "Bytes"
    def to_jsonschema(self): return {"type": "string", "contentEncoding": "base64"}

@dataclass(frozen=True)
class DateSchema(Schema):
    def __repr__(self): return "Date"
    def to_jsonschema(self): return {"type": "string", "format": "date"}
    def coerce(self, value: Any) -> Any:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        raise TypeError(f"Cannot coerce {value!r} to date")

@dataclass(frozen=True)
class DateTimeSchema(Schema):
    def __repr__(self): return "DateTime"
    def to_jsonschema(self): return {"type": "string", "format": "date-time"}
    def coerce(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value
        raise TypeError(f"Cannot coerce {value!r} to datetime")

@dataclass(frozen=True)
class ArraySchema(Schema):
    items: Schema
    kind: str = "list"  # "list", "tuple", or "set"
    def __repr__(self): return f"{self.kind.capitalize()}[{self.items!r}]"
    def to_jsonschema(self):
        js = {"type": "array", "items": self.items.to_jsonschema()}
        if self.kind == "set":
            js["uniqueItems"] = True
        return js
    def merge(self, other: Schema) -> Schema:
        if isinstance(other, ArraySchema) and self.kind == other.kind:
            return ArraySchema(items=self.items.merge(other.items), kind=self.kind)
        return super().merge(other)
    def coerce(self, value: Any) -> Any:
        if self.kind == "list" and isinstance(value, list):
            return [self.items.coerce(v) for v in value]
        if self.kind == "tuple" and isinstance(value, (list, tuple)):
            return tuple(self.items.coerce(v) for v in value)
        if self.kind == "set" and isinstance(value, (list, set, tuple)):
            return {self.items.coerce(v) for v in value}
        raise TypeError(f"Cannot coerce {type(value).__name__} to {self.kind}")

@dataclass(frozen=True)
class MapSchema(Schema):
    key: Schema
    value: Schema
    def __repr__(self): return f"Map[{self.key!r} → {self.value!r}]"
    def to_jsonschema(self):
        return {
            "type": "object",
            "additionalProperties": self.value.to_jsonschema()
        }
    def merge(self, other: Schema) -> Schema:
        if isinstance(other, MapSchema):
            return MapSchema(self.key.merge(other.key), self.value.merge(other.value))
        return super().merge(other)

@dataclass(frozen=True)
class ObjectSchema(Schema):
    properties: Dict[str, Schema] = field(default_factory=dict)
    optional: Set[str] = field(default_factory=set)  # fields that may be missing / null

    def __repr__(self):
        parts = []
        for k in sorted(self.properties):
            opt = "?" if k in self.optional else ""
            parts.append(f"{k}{opt}: {self.properties[k]!r}")
        return "{" + ", ".join(parts) + "}"

    def to_jsonschema(self):
        required = [k for k in self.properties if k not in self.optional]
        return {
            "type": "object",
            "properties": {k: v.to_jsonschema() for k, v in self.properties.items()},
            "required": required,
            "additionalProperties": False,
        }

    def merge(self, other: Schema) -> Schema:
        if not isinstance(other, ObjectSchema):
            return super().merge(other)
        keys = set(self.properties) | set(other.properties)
        props: Dict[str, Schema] = {}
        optional: Set[str] = set()
        for k in keys:
            if k in self.properties and k in other.properties:
                props[k] = self.properties[k].merge(other.properties[k])
            elif k in self.properties:
                props[k] = self.properties[k]
                optional.add(k)
            else:
                props[k] = other.properties[k]
                optional.add(k)
        optional |= self.optional | other.optional
        return ObjectSchema(props, optional)

    def coerce(self, value: Any) -> Any:
        if not isinstance(value, Mapping):
            if hasattr(value, "__dict__"):
                value = vars(value)
            else:
                raise TypeError("ObjectSchema expects a mapping-like value")
        out = {}
        for k, sch in self.properties.items():
            if k in value and value[k] is not None:
                out[k] = sch.coerce(value[k])
            elif k in self.optional:
                out[k] = None
            else:
                raise KeyError(f"Missing required field: {k}")
        return out

@dataclass(frozen=True)
class UnionSchema(Schema):
    variants: Tuple[Schema, ...]
    def __repr__(self):
        return " | ".join(repr(v) for v in self.variants)

    @staticmethod
    def _flatten(s: Schema, acc: list[Schema]) -> None:
        if isinstance(s, UnionSchema):
            for v in s.variants:
                UnionSchema._flatten(v, acc)
        else:
            acc.append(s)

    @staticmethod
    def of(*schemas: Schema) -> Schema:
        flat: list[Schema] = []
        for s in schemas:
            UnionSchema._flatten(s, flat)
        uniq: Dict[str, Schema] = {repr(s): s for s in flat}
        has_int = any(isinstance(s, IntSchema) for s in uniq.values())
        has_float = any(isinstance(s, FloatSchema) for s in uniq.values())
        if has_int and has_float:
            uniq = {k: v for k, v in uniq.items() if not isinstance(v, IntSchema)}
        if len(uniq) == 1:
            return next(iter(uniq.values()))
        ordered = sorted(uniq.values(), key=lambda s: repr(s))
        return UnionSchema(tuple(ordered))

    def to_jsonschema(self):
        return {"anyOf": [v.to_jsonschema() for v in self.variants]}

# ------------------------------
# Inference
# ------------------------------

def _infer_single(value: Any) -> Schema:
    if value is None:
        return NullSchema()
    if isinstance(value, bool):
        return BoolSchema()
    if isinstance(value, int) and not isinstance(value, bool):
        return IntSchema()
    if isinstance(value, float):
        return FloatSchema()
    if isinstance(value, (str,)):
        return StringSchema()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return BytesSchema()
    if isinstance(value, datetime):
        return DateTimeSchema()
    if isinstance(value, date):
        return DateSchema()

    if isinstance(value, Mapping):
        if all(isinstance(k, str) for k in value.keys()):
            props: Dict[str, Schema] = {}
            optional: Set[str] = set()
            for k, v in value.items():
                if v is None:
                    optional.add(k)
                    props[k] = NullSchema()
                else:
                    props[k] = _infer_single(v)
            return ObjectSchema(props, optional)
        else:
            key_s: Schema | None = None
            val_s: Schema | None = None
            for k, v in value.items():
                ks = _infer_single(k)
                vs = _infer_single(v)
                key_s = ks if key_s is None else key_s.merge(ks)
                val_s = vs if val_s is None else val_s.merge(vs)
            if key_s is None:
                return MapSchema(StringSchema(), NullSchema())
            return MapSchema(key_s, val_s if val_s is not None else NullSchema())

    if isinstance(value, (list, tuple, set, frozenset)):
        kind = "list" if isinstance(value, list) else "tuple" if isinstance(value, tuple) else "set"
        item_schema: Schema | None = None
        for item in value:
            s = _infer_single(item)
            item_schema = s if item_schema is None else item_schema.merge(s)
        if item_schema is None:
            item_schema = NullSchema()
        return ArraySchema(item_schema, kind=kind)

    if hasattr(value, "__dict__"):
        return _infer_single(vars(value))

    return StringSchema()

def deduce_schema(values: Sequence[Any]) -> Schema:
    """Infer a schema from a list/sequence of Python objects.
    - If all values are None, returns Null.
    - Otherwise, merges types across all samples.
    """
    if not values:
        return NullSchema()
    merged: Schema | None = None
    all_null = True
    for v in values:
        s = _infer_single(v)
        if not isinstance(s, NullSchema):
            all_null = False
        merged = s if merged is None else merged.merge(s)
    return NullSchema() if all_null else merged

# ------------------------------
# Mapping/coercion utilities
# ------------------------------

def coerce_to_schema(value: Any, schema: Schema) -> Any:
    """Attempt to coerce/map a Python value into the given schema recursively.
    For UnionSchema, tries each variant in order.
    """
    if isinstance(schema, UnionSchema):
        last_err = None
        for variant in schema.variants:
            try:
                return coerce_to_schema(value, variant)
            except Exception as e:  # noqa: BLE001 - keep simple for library
                last_err = e
        raise TypeError(f"Value does not match any union variant: {last_err}")
    return schema.coerce(value)

# ------------------------------
# Pretty helpers
# ------------------------------

def schema_repr(schema: Schema) -> str:
    """Stable, concise representation for printing."""
    return repr(schema)

