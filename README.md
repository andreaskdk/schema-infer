# schema-infer

Infer schemas from Python objects (incl. nested/compound types). Merge across samples. Export JSON‑Schema‑like dicts. Optionally coerce values to the inferred schema.

## Features
- Deduce types from Python objects, nested structures, and collections
- Merge heterogeneous samples (e.g., `int + float -> Float`, `mixed -> Union`)
- If only nulls are present, the schema is `Null`
- Distinguish optional object fields when keys are missing or values are `None`
- Export to a JSON‑Schema‑like structure
- Best‑effort coercion utilities

## Install

Install directly from GitHub:

```bash
pip install git+https://github.com/andreaskdk/schema-infer.git
```


Or add to pyproject.toml:

```
[project]
dependencies = [
  "schema-infer @ git+https://github.com/andreaskdk/schema-infer.git"
]
```

