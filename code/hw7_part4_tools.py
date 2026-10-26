import ast
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, DivisionByZero, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

PRICING_URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
PRICING_FINAL_URL = "https://lyftbikes.com/pricing"
ALLOWED_POLICY_LOCATIONS = {
    ("www.lyft.com", "/bikes/bay-wheels/pricing"),
    ("lyftbikes.com", "/pricing"),
    ("www.lyftbikes.com", "/pricing"),
}
MAX_POLICY_BYTES = 3_000_000
MAX_SQL_ROWS = 100
MAX_CSV_BYTES = 100_000_000
MAX_CSV_ROWS = 250_000
MAX_SQL_STEPS = 500_000
MAX_EXPRESSION_LENGTH = 256
MAX_CALCULATOR_ABS_VALUE = Decimal("1e15")
CALCULATOR_PATTERN = re.compile(r"^[0-9+\-*/().\s]+$")
WORD_PATTERN = re.compile(r"[a-z0-9]+")
MONEY_PATTERN = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
MONTHLY_RATE_PATTERN = re.compile(
    r"\$\s*(?P<amount>\d+(?:\.\d+)?)\s*/\s*month",
    re.IGNORECASE,
)
CLASSIC_MEMBER_RATE_PATTERN = re.compile(
    r"\b(?P<minutes>\d+)\s*"
    r"(?:min|mins|minute|minutes)\s+"
    r"(?:are\s+)?(?:free|included)\s*,?\s*"
    r"then\s*\$\s*(?P<rate>\d+(?:\.\d+)?)\s*/\s*"
    r"(?:min|minute)",
    re.IGNORECASE,
)
EBIKE_MEMBER_RATE_PATTERN = re.compile(
    r"\bfree\s+unlocks?\s*\+\s*"
    r"\$\s*(?P<rate>\d+(?:\.\d+)?)\s*/\s*"
    r"(?:min|minute)",
    re.IGNORECASE,
)


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CsvSqlArguments(StrictArguments):
    sql: str = Field(min_length=1, max_length=10_000)

    @field_validator("sql")
    @classmethod
    def sql_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sql must not be blank")

        return value.strip()


class PolicyRetrieverArguments(StrictArguments):
    url: str = Field(min_length=1, max_length=500)
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=3, ge=1, le=8)

    @field_validator("url")
    @classmethod
    def url_must_be_official_pricing_page(cls, value: str) -> str:
        normalized = value.strip()
        _validate_policy_url(normalized)

        return normalized

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")

        return value.strip()


class CalculatorArguments(StrictArguments):
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
    units: str | None = Field(default=None, max_length=64)

    @field_validator("expression")
    @classmethod
    def expression_must_match_whitelist(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("expression must not be blank")

        if CALCULATOR_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "expression must match ^[0-9+\\-*/().\\s]+$"
            )

        return normalized

    @field_validator("units")
    @classmethod
    def units_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("units must not be blank")

        return normalized


TOOL_ARGUMENT_MODELS: dict[str, type[StrictArguments]] = {
    "csv_sql": CsvSqlArguments,
    "policy_retriever": PolicyRetrieverArguments,
    "calculator": CalculatorArguments,
}

TOOL_DESCRIPTIONS = {
    "csv_sql": (
        "Run one bounded, read-only SELECT query against the uploaded "
        "CSV exposed as the fixed SQLite table trips."
    ),
    "policy_retriever": (
        "Retrieve short, citable passages from the official Bay Wheels "
        "pricing page."
    ),
    "calculator": (
        "Safely evaluate basic arithmetic using only numbers, parentheses, "
        "and +, -, *, or /."
    ),
}


def _schema(name: str) -> dict[str, Any]:
    parameters = TOOL_ARGUMENT_MODELS[name].model_json_schema()
    parameters.pop("title", None)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "parameters": parameters,
        },
    }


PART4_TOOL_SCHEMAS = [
    _schema(name)
    for name in ("csv_sql", "policy_retriever", "calculator")
]


class Part4ToolValidationError(ValueError):
    """Raised before a Part 4 tool performs any work."""


def validate_part4_inputs(name: str, inputs: Any) -> dict[str, Any]:
    if name not in TOOL_ARGUMENT_MODELS:
        raise Part4ToolValidationError(f"unknown tool: {name}")

    if not isinstance(inputs, dict):
        raise Part4ToolValidationError("tool inputs must be a JSON object")

    try:
        validated = TOOL_ARGUMENT_MODELS[name].model_validate(inputs)
    except ValidationError as exc:
        extra = sorted(set(inputs) - set(TOOL_ARGUMENT_MODELS[name].model_fields))

        if extra:
            detail = "unknown field(s): " + ", ".join(extra)
        else:
            error = exc.errors(include_url=False)[0]
            location = ".".join(str(item) for item in error.get("loc", ()))
            detail = f"{location or 'arguments'}: {error.get('msg', 'invalid value')}"

        raise Part4ToolValidationError(
            f"schema validation failed for {name}: {detail}"
        ) from exc

    return validated.model_dump()


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _success(data: Any, *, source: str) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "source": source,
        "ts": _now_utc(),
    }


def _failure(error: str, *, source: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "success": False,
        "error": error,
        "ts": _now_utc(),
    }

    if source is not None:
        result["source"] = source

    return result


def _validate_policy_url(url: str) -> None:
    parsed = urlsplit(url)
    location = (parsed.hostname or "", parsed.path.rstrip("/") or "/")

    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or location not in ALLOWED_POLICY_LOCATIONS
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "url must be the official Bay Wheels/Lyft Bikes pricing page"
        )


def _sql_code_tokens(sql: str) -> tuple[str, list[str]]:
    characters: list[str] = []
    state = "normal"
    index = 0
    semicolon_index: int | None = None

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if state == "normal":
            if char == "'":
                state = "single"
                characters.append(" ")
            elif char == '"':
                state = "double"
                characters.append(" ")
            elif char == "`":
                state = "backtick"
                characters.append(" ")
            elif char == "[":
                state = "bracket"
                characters.append(" ")
            elif char == "-" and next_char == "-":
                raise ValueError("SQL comments are not allowed")
            elif char == "/" and next_char == "*":
                raise ValueError("SQL comments are not allowed")
            elif char == ";":
                if semicolon_index is not None:
                    raise ValueError("only one SQL statement is allowed")

                semicolon_index = index
                characters.append(" ")
            else:
                characters.append(char)
        elif state == "single":
            characters.append(" ")

            if char == "'":
                if next_char == "'":
                    characters.append(" ")
                    index += 1
                else:
                    state = "normal"
        elif state == "double":
            characters.append(" ")

            if char == '"':
                if next_char == '"':
                    characters.append(" ")
                    index += 1
                else:
                    state = "normal"
        elif state == "backtick":
            characters.append(" ")

            if char == "`":
                state = "normal"
        else:
            characters.append(" ")

            if char == "]":
                state = "normal"

        index += 1

    if state != "normal":
        raise ValueError("SQL contains an unterminated quoted value")

    if semicolon_index is not None and sql[semicolon_index + 1 :].strip():
        raise ValueError("only one SQL statement is allowed")

    statement = (
        sql[:semicolon_index].strip()
        if semicolon_index is not None
        else sql.strip()
    )
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", "".join(characters).lower())

    return statement, tokens


FORBIDDEN_SQL_TOKENS = {
    "alter",
    "attach",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "insert",
    "pragma",
    "reindex",
    "replace",
    "update",
    "vacuum",
}

ALLOWED_SQL_FUNCTIONS = {
    "abs",
    "avg",
    "cast",
    "coalesce",
    "count",
    "date",
    "datetime",
    "ifnull",
    "instr",
    "julianday",
    "length",
    "lower",
    "ltrim",
    "max",
    "min",
    "nullif",
    "replace",
    "round",
    "rtrim",
    "strftime",
    "substr",
    "substring",
    "sum",
    "time",
    "total",
    "trim",
    "typeof",
    "upper",
}


def _validate_readonly_sql(sql: str) -> str:
    statement, tokens = _sql_code_tokens(sql)

    if not tokens or tokens[0] not in {"select", "with"}:
        raise ValueError("SQL must be one SELECT or WITH...SELECT statement")

    forbidden = sorted(set(tokens) & FORBIDDEN_SQL_TOKENS)

    if forbidden:
        raise ValueError("forbidden SQL keyword: " + forbidden[0].upper())

    if "select" not in tokens:
        raise ValueError("WITH statement must end in a SELECT query")

    return statement


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _load_csv(connection: sqlite3.Connection, csv_path: Path) -> None:
    if not csv_path.is_file():
        raise ValueError("uploaded CSV is unavailable")

    size = csv_path.stat().st_size

    if size > MAX_CSV_BYTES:
        raise ValueError(f"uploaded CSV exceeds {MAX_CSV_BYTES} bytes")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames

        if not fieldnames:
            raise ValueError("uploaded CSV has no header")

        if any(not name or not name.strip() for name in fieldnames):
            raise ValueError("uploaded CSV has a blank column name")

        if len(set(fieldnames)) != len(fieldnames):
            raise ValueError("uploaded CSV has duplicate column names")

        columns = ", ".join(
            f"{_quote_identifier(name)} TEXT"
            for name in fieldnames
        )
        connection.execute(f"CREATE TABLE trips ({columns})")
        placeholders = ", ".join("?" for _ in fieldnames)
        insert_sql = f"INSERT INTO trips VALUES ({placeholders})"
        row_count = 0

        for row_count, row in enumerate(reader, start=1):
            if row_count > MAX_CSV_ROWS:
                raise ValueError(f"uploaded CSV exceeds {MAX_CSV_ROWS} rows")

            connection.execute(
                insert_sql,
                [row.get(name) for name in fieldnames],
            )


def _readonly_authorizer(
    action: int,
    arg1: str | None,
    arg2: str | None,
    _database: str | None,
    _trigger: str | None,
) -> int:
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK

    if action == sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_OK if arg1 == "trips" else sqlite3.SQLITE_DENY

    if action == sqlite3.SQLITE_FUNCTION:
        function_name = (arg2 or arg1 or "").lower()

        return (
            sqlite3.SQLITE_OK
            if function_name in ALLOWED_SQL_FUNCTIONS
            else sqlite3.SQLITE_DENY
        )

    return sqlite3.SQLITE_DENY


def csv_sql(
    inputs: Any,
    *,
    csv_path: str | Path | None = None,
) -> dict[str, Any]:
    source = "uploaded.csv"

    try:
        arguments = validate_part4_inputs("csv_sql", inputs)
        statement = _validate_readonly_sql(arguments["sql"])
        selected_path = Path(
            csv_path or os.getenv("HW7_PART4_CSV_PATH", "")
        )

        if not str(selected_path):
            raise ValueError("uploaded CSV path is not configured")

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row

        try:
            _load_csv(connection, selected_path)
            connection.enable_load_extension(False)
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 10_000)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
            connection.execute("PRAGMA query_only = ON")
            connection.set_authorizer(_readonly_authorizer)
            connection.set_progress_handler(
                lambda: 1,
                MAX_SQL_STEPS,
            )
            bounded = (
                "SELECT * FROM ("
                + statement
                + f") AS part4_result LIMIT {MAX_SQL_ROWS}"
            )
            rows = [dict(row) for row in connection.execute(bounded)]
        finally:
            connection.close()

        return _success(
            {
                "rows": rows,
                "row_count": len(rows),
                "source": source,
            },
            source=source,
        )
    except (OSError, sqlite3.Error, ValueError, Part4ToolValidationError) as exc:
        return _failure(f"csv_sql failed: {exc}", source=source)


@dataclass(frozen=True)
class FetchedPage:
    content: bytes
    final_url: str
    status_code: int


PageFetcher = Callable[[str], FetchedPage]


def fetch_pricing_page(url: str) -> FetchedPage:
    _validate_policy_url(url)
    headers = {
        "User-Agent": "DATA260-HW7-policy-capture/1.0",
        "Accept": "text/html,application/xhtml+xml",
    }

    with requests.get(
        url,
        headers=headers,
        timeout=(5, 20),
        stream=True,
        allow_redirects=True,
    ) as response:
        response.raise_for_status()

        if len(response.history) > 5:
            raise ValueError("pricing page exceeded five redirects")

        _validate_policy_url(response.url)
        content_type = response.headers.get("Content-Type", "").lower()

        if "html" not in content_type:
            raise ValueError(
                f"pricing page returned unexpected content type: {content_type}"
            )

        content_length = response.headers.get("Content-Length")

        if content_length and int(content_length) > MAX_POLICY_BYTES:
            raise ValueError(
                f"pricing page exceeds {MAX_POLICY_BYTES} bytes"
            )

        content = bytearray()

        for chunk in response.iter_content(chunk_size=65_536):
            content.extend(chunk)

            if len(content) > MAX_POLICY_BYTES:
                raise ValueError(
                    f"pricing page exceeds {MAX_POLICY_BYTES} bytes"
                )

    return FetchedPage(
        content=bytes(content),
        final_url=response.url,
        status_code=response.status_code,
    )


class _PassageParser(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "main",
        "p",
        "section",
    }
    SKIP_TAGS = {"script", "style", "svg", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, list[str]]] = []
        self.skip_depth = 0
        self.passages: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        _attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered = tag.lower()

        if lowered in self.SKIP_TAGS:
            self.skip_depth += 1

        self.stack.append((lowered, []))

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return

        for _, pieces in self.stack:
            pieces.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()

        if not self.stack:
            return

        index = next(
            (
                position
                for position in range(len(self.stack) - 1, -1, -1)
                if self.stack[position][0] == lowered
            ),
            None,
        )

        if index is None:
            return

        closed = self.stack[index:]
        self.stack = self.stack[:index]

        for closed_tag, pieces in closed:
            if closed_tag in self.BLOCK_TAGS:
                text = " ".join(" ".join(pieces).split())

                if 2 <= len(text) <= 2_000:
                    self.passages.append(text)

        if lowered in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1


def parse_policy_passages(html: bytes, *, source: str) -> list[dict[str, Any]]:
    _validate_policy_url(source)
    parser = _PassageParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    unique: list[str] = []
    seen: set[str] = set()

    for passage in parser.passages:
        key = passage.casefold()

        if key not in seen:
            seen.add(key)
            unique.append(passage)

    return [
        {
            "text": text,
            "source": source,
        }
        for text in unique
    ]


def _passage_score(query: str, text: str) -> float:
    query_words = set(WORD_PATTERN.findall(query.lower()))
    text_words = set(WORD_PATTERN.findall(text.lower()))

    if not query_words:
        return 0.0

    overlap = len(query_words & text_words) / len(query_words)
    phrase_bonus = 0.35 if query.lower() in text.lower() else 0.0
    price_bonus = 0.1 if "$" in text else 0.0

    return round(overlap + phrase_bonus + price_bonus, 6)


def retrieve_policy_passages(
    passages: list[dict[str, Any]],
    query: str,
    k: int,
) -> list[dict[str, Any]]:
    scored = [
        {
            **passage,
            "score": _passage_score(query, passage["text"]),
        }
        for passage in passages
    ]
    scored.sort(
        key=lambda item: (
            -item["score"],
            len(item["text"]),
            item["text"],
        )
    )

    return scored[:k]


def policy_retriever(
    inputs: Any,
    *,
    fetcher: PageFetcher = fetch_pricing_page,
) -> dict[str, Any]:
    source: str | None = None

    try:
        arguments = validate_part4_inputs("policy_retriever", inputs)
        page = fetcher(arguments["url"])
        source = page.final_url
        _validate_policy_url(source)
        passages = parse_policy_passages(page.content, source=source)

        if not passages:
            raise ValueError("pricing page contained no retrievable text")

        selected = retrieve_policy_passages(
            passages,
            arguments["query"],
            arguments["k"],
        )

        return _success(
            {
                "passages": selected,
                "query": arguments["query"],
            },
            source=source,
        )
    except (
        OSError,
        requests.RequestException,
        ValueError,
        Part4ToolValidationError,
    ) as exc:
        return _failure(
            f"policy_retriever failed: {type(exc).__name__}: {exc}",
            source=source,
        )


def _evaluate_node(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)

    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        value = Decimal(str(node.value))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate_node(node.operand)
        value = operand if isinstance(node.op, ast.UAdd) else -operand
    elif isinstance(node, ast.BinOp) and isinstance(
        node.op,
        (ast.Add, ast.Sub, ast.Mult, ast.Div),
    ):
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)

        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        else:
            if right == 0:
                raise ValueError("division by zero")

            value = left / right
    else:
        raise ValueError(
            "only +, -, *, /, parentheses, and numeric literals are allowed"
        )

    if not value.is_finite():
        raise ValueError("calculator result must be finite")

    if abs(value) > MAX_CALCULATOR_ABS_VALUE:
        raise ValueError("calculator result exceeds the safe numeric range")

    return value


def calculator(inputs: Any) -> dict[str, Any]:
    source = "safe-ast-calculator"

    try:
        arguments = validate_part4_inputs("calculator", inputs)
        parsed = ast.parse(arguments["expression"], mode="eval")

        if sum(1 for _ in ast.walk(parsed)) > 100:
            raise ValueError("expression is too complex")

        value = _evaluate_node(parsed)
        number: int | float = (
            int(value)
            if value == value.to_integral_value()
            else float(value)
        )

        if isinstance(number, float) and not math.isfinite(number):
            raise ValueError("calculator result must be finite")

        return _success(
            {
                "value": number,
                "units": arguments["units"],
                "expression": arguments["expression"],
            },
            source=source,
        )
    except (
        DivisionByZero,
        InvalidOperation,
        Part4ToolValidationError,
        SyntaxError,
        ValueError,
    ) as exc:
        return _failure(f"calculator failed: {exc}", source=source)


def capture_policy_snapshot(
    *,
    url: str,
    html_path: Path,
    snapshot_path: Path,
    fetcher: PageFetcher = fetch_pricing_page,
    capture_kind: str = "official_network_capture",
) -> dict[str, Any]:
    _validate_policy_url(url)
    page = fetcher(url)
    passages = parse_policy_passages(page.content, source=page.final_url)
    rules = extract_pricing_rules(passages)
    exact_pricing_passages: list[str] = []

    for rule in rules.values():
        for passage in rule.get(
            "evidence_passages",
            [rule["evidence"]],
        ):
            if passage not in exact_pricing_passages:
                exact_pricing_passages.append(passage)
    captured_utc = datetime.now(timezone.utc)
    captured_pdt = captured_utc.astimezone(ZoneInfo("America/Los_Angeles"))
    html_hash = hashlib.sha256(page.content).hexdigest()
    payload = {
        "capture_kind": capture_kind,
        "requested_url": url,
        "final_url": page.final_url,
        "http_status": page.status_code,
        "captured_at_utc": captured_utc.isoformat().replace("+00:00", "Z"),
        "captured_at_pdt": captured_pdt.isoformat(),
        "html_bytes": len(page.content),
        "html_sha256": html_hash,
        "html_file": html_path.name,
        "exact_pricing_passages": exact_pricing_passages,
        "pricing_rules": rules,
    }
    html_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_bytes(page.content)
    snapshot_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return payload


def _smallest_passage(
    passages: list[dict[str, Any]],
    predicate: Callable[[str], bool],
    label: str,
) -> str:
    matches = [
        passage["text"]
        for passage in passages
        if predicate(passage["text"].lower())
    ]

    if not matches:
        raise ValueError(f"pricing page is missing evidence for {label}")

    return min(matches, key=lambda text: (len(text), text))


def _normalized_passage(text: str) -> str:
    return " ".join(text.casefold().split())


def _smallest_scoped_passage(
    passages: list[dict[str, Any]],
    *,
    scope: str,
    predicate: Callable[[str], bool],
    label: str,
) -> str:
    normalized_scope = _normalized_passage(scope)
    matches = [
        passage["text"]
        for passage in passages
        if predicate(passage["text"])
        and _normalized_passage(passage["text"]) in normalized_scope
    ]

    if not matches:
        raise ValueError(
            f"pricing page is missing Month pass evidence for {label}"
        )

    return min(matches, key=lambda text: (len(text), text))


def _pattern_values(
    text: str,
    pattern: re.Pattern[str],
    group: str,
) -> list[Decimal]:
    return [
        Decimal(match.group(group))
        for match in pattern.finditer(text)
    ]


def _require_expected_pattern_value(
    text: str,
    *,
    pattern: re.Pattern[str],
    group: str,
    expected: Decimal,
    label: str,
) -> Decimal:
    values = _pattern_values(text, pattern, group)

    if expected not in values:
        raise ValueError(
            f"{label} evidence does not contain the required value {expected}"
        )

    return expected


def _money_values(text: str) -> list[Decimal]:
    return [Decimal(value) for value in MONEY_PATTERN.findall(text)]


def _find_amount(
    values: list[Decimal],
    *,
    expected: Decimal,
    label: str,
) -> Decimal:
    if expected not in values:
        raise ValueError(f"{label} evidence does not contain ${expected}")

    return expected


def extract_pricing_rules(
    passages: list[dict[str, Any]],
) -> dict[str, Any]:
    month_pass_scope = _smallest_passage(
        passages,
        lambda text: (
            "month pass" in text
            and "classic bike prices" in text
            and "ebike prices" in text
        ),
        "Month pass pricing context",
    )
    monthly = _smallest_scoped_passage(
        passages,
        scope=month_pass_scope,
        predicate=lambda text: Decimal("29")
        in _pattern_values(text, MONTHLY_RATE_PATTERN, "amount"),
        label="monthly membership price",
    )
    classic_non_member = _smallest_passage(
        passages,
        lambda text: (
            "classic" in text
            and "unlock" in text
            and "$1" in text
            and "$0.19" in text
        ),
        "classic non-member pricing",
    )
    classic_member_scope = _smallest_scoped_passage(
        passages,
        scope=month_pass_scope,
        predicate=lambda text: any(
            "classic bike prices" in text.casefold()
            and match.group("minutes") == "45"
            and Decimal(match.group("rate")) == Decimal("0.17")
            for match in CLASSIC_MEMBER_RATE_PATTERN.finditer(text)
        ),
        label="member Classic pricing section",
    )
    classic_member = _smallest_scoped_passage(
        passages,
        scope=classic_member_scope,
        predicate=lambda text: any(
            match.group("minutes") == "45"
            and Decimal(match.group("rate")) == Decimal("0.17")
            for match in CLASSIC_MEMBER_RATE_PATTERN.finditer(text)
        ),
        label="member classic inclusion and overage",
    )
    ebike_non_member = _smallest_passage(
        passages,
        lambda text: (
            any(term in text for term in ("ebike", "e-bike", "electric bike"))
            and "unlock" in text
            and "$1" in text
            and "$0.49" in text
        ),
        "non-member ebike pricing",
    )
    ebike_member_scope = _smallest_scoped_passage(
        passages,
        scope=month_pass_scope,
        predicate=lambda text: (
            "ebike prices" in text.casefold()
            and Decimal("0.17")
            in _pattern_values(text, EBIKE_MEMBER_RATE_PATTERN, "rate")
        ),
        label="member Ebike pricing section",
    )
    ebike_member = _smallest_scoped_passage(
        passages,
        scope=ebike_member_scope,
        predicate=lambda text: Decimal("0.17")
        in _pattern_values(text, EBIKE_MEMBER_RATE_PATTERN, "rate"),
        label="member ebike pricing",
    )
    scoped_classic_rates = {
        Decimal(match.group("rate"))
        for match in CLASSIC_MEMBER_RATE_PATTERN.finditer(
            classic_member_scope
        )
        if match.group("minutes") == "45"
    }

    if scoped_classic_rates != {Decimal("0.17")}:
        formatted = ", ".join(
            str(value)
            for value in sorted(scoped_classic_rates)
        ) or "none"
        raise ValueError(
            "contradictory member classic evidence in Month pass context: "
            f"45-minute rates were {formatted}"
        )

    included_minutes = next(
        int(match.group("minutes"))
        for match in CLASSIC_MEMBER_RATE_PATTERN.finditer(classic_member)
        if Decimal(match.group("rate")) == Decimal("0.17")
    )

    return {
        "month_pass": {
            "amount": str(
                _require_expected_pattern_value(
                    monthly,
                    pattern=MONTHLY_RATE_PATTERN,
                    group="amount",
                    expected=Decimal("29"),
                    label="month pass",
                )
            ),
            "billing_period": "month",
            "evidence": monthly,
        },
        "classic_non_member": {
            "unlock_fee": str(
                _find_amount(
                    _money_values(classic_non_member),
                    expected=Decimal("1"),
                    label="classic unlock",
                )
            ),
            "per_minute": str(
                _find_amount(
                    _money_values(classic_non_member),
                    expected=Decimal("0.19"),
                    label="classic non-member rate",
                )
            ),
            "evidence": classic_non_member,
        },
        "classic_member": {
            "included_minutes": included_minutes,
            "overage_per_minute": str(
                _require_expected_pattern_value(
                    classic_member,
                    pattern=CLASSIC_MEMBER_RATE_PATTERN,
                    group="rate",
                    expected=Decimal("0.17"),
                    label="classic member overage",
                )
            ),
            "evidence": classic_member,
            "evidence_passages": [
                month_pass_scope,
                classic_member_scope,
                classic_member,
            ],
            "evidence_scope": "Month pass",
        },
        "ebike_non_member": {
            "unlock_fee": str(
                _find_amount(
                    _money_values(ebike_non_member),
                    expected=Decimal("1"),
                    label="ebike unlock",
                )
            ),
            "per_minute": str(
                _find_amount(
                    _money_values(ebike_non_member),
                    expected=Decimal("0.49"),
                    label="ebike non-member rate",
                )
            ),
            "evidence": ebike_non_member,
        },
        "ebike_member": {
            "unlock_fee": "0",
            "per_minute": str(
                _require_expected_pattern_value(
                    ebike_member,
                    pattern=EBIKE_MEMBER_RATE_PATTERN,
                    group="rate",
                    expected=Decimal("0.17"),
                    label="ebike member rate",
                )
            ),
            "evidence": ebike_member,
            "evidence_passages": [
                month_pass_scope,
                ebike_member_scope,
                ebike_member,
            ],
            "evidence_scope": "Month pass",
        },
    }


def verify_snapshot_hash(snapshot_path: Path) -> bool:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    html_path = snapshot_path.parent / payload["html_file"]

    return hashlib.sha256(html_path.read_bytes()).hexdigest() == payload[
        "html_sha256"
    ]
