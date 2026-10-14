"""Base for anything a model produces as structured output.

Some models (NVIDIA-hosted Nemotron, in tool-output mode) send a nested object or list as
a JSON-encoded string: `"remedy": "{\"type\": \"partial_refund\", ...}"` instead of the
object itself. The content is right; only the encoding is off. Decoding it here keeps a
correct verdict from burning every output retry. A field typed `str` is never touched.
"""

import json
from typing import Any

from pydantic import BaseModel, model_validator


def _wants_text(annotation: Any) -> bool:
    return annotation is str or annotation == (str | None)


class ModelOutput(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _decode_json_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for name, field in cls.model_fields.items():
            value = out.get(name)
            if (
                isinstance(value, str)
                and value.lstrip()[:1] in ("{", "[")
                and not _wants_text(field.annotation)
            ):
                try:
                    out[name] = json.loads(value)
                except ValueError:
                    pass  # leave it for normal validation to reject
        return out
