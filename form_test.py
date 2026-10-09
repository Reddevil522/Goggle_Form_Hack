
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

# ===== CONFIGURATION =====
FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSeae8i3cRMwI_GIXMOABebQ-YIOR6yTeROiiTOzC1dU9uavaA/viewform"
)

EXPECTED_TITLE = "Social Media and English Usage among Gen Z | Kiran Muley"
CSV_PATH = "GenZ_fixed.csv"
DRY_RUN = False
DELAY = 1.5

# Google Forms internal item types
TEXT, PARAGRAPH, CHOICE, DROPDOWN, CHECKBOX, SCALE, GRID, PAGE_BREAK = (
    0, 1, 2, 3, 4, 5, 7, 8
)

SIMPLE_TYPES = {TEXT, PARAGRAPH, CHOICE, DROPDOWN, SCALE}


def clean_url(url):
    return url.split("?")[0]


def read_form(url):
    """Download the public form and extract its structure."""
    response = requests.get(clean_url(url), timeout=30)
    response.raise_for_status()
    html = response.text

    title_match = re.search(r"<title>(.*?)</title>", html, re.S)
    title = title_match.group(1).strip() if title_match else ""

    data_match = re.search(
        r"FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);\s*</script>",
        html,
        re.S,
    )

    if not data_match:
        raise ValueError(
            "Could not read the form structure. "
            "Check that the form URL is correct and publicly accessible."
        )

    data = json.loads(data_match.group(1))
    items = data[1][1]

    fields = []
    pages = 1

    for item in items:
        item_type = item[3]
        item_title = (item[1] or "").strip()

        if item_type == PAGE_BREAK:
            pages += 1

        elif item_type in SIMPLE_TYPES:
            fields.append(("single", item_title, item[4][0][0]))

        elif item_type == CHECKBOX:
            fields.append(("multi", item_title, item[4][0][0]))

        elif item_type == GRID:
            rows = [
                (question[0], question[3][0])
                for question in item[4]
            ]
            fields.append(("grid", item_title, rows))

    return title, fields, pages


def grid_prefix(form_title):
    return (
        "Informal Communication"
        if form_title.startswith("Informal")
        else "Formal Academic Communication"
    )


def check_columns(df, fields):
    missing = []

    for kind, field_title, target in fields:
        if kind == "grid":
            for _, row_label in target:
                key = f"{grid_prefix(field_title)} [{row_label}]"
                if key not in df.columns:
                    missing.append(key)

        elif field_title not in df.columns:
            missing.append(field_title)

    if missing:
        raise ValueError(
            "CSV columns missing:\n" + "\n".join(missing)
        )


def build_payload(row, fields, pages):
    payload = []

    for kind, field_title, target in fields:
        if kind == "single":
            value = str(row[field_title]).strip()

            if value:
                payload.append((f"entry.{target}", value))

        elif kind == "multi":
            values = re.split(r",\s*", str(row[field_title]).strip())

            for value in values:
                if value:
                    payload.append((f"entry.{target}", value))

        elif kind == "grid":
            for entry_id, row_label in target:
                key = f"{grid_prefix(field_title)} [{row_label}]"
                payload.append(
                    (f"entry.{entry_id}", str(row[key]).strip())
                )

    payload.append(
        ("pageHistory", ",".join(str(i) for i in range(pages)))
    )
    payload.append(("fvv", "1"))

    return payload


def main():
    path = Path(CSV_PATH)

    if not path.exists():
        raise FileNotFoundError(
            f"CSV not found: {path.resolve()}"
        )

    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    df.columns = df.columns.str.strip()

    if df.empty:
        raise ValueError("The CSV file contains no response rows.")

    title, fields, pages = read_form(FORM_URL)

    print("Form title:", title)
    print("Fields found:", len(fields), "| Pages:", pages)

    # Verify the exact form title
    normalized_title = re.sub(r"\s*-\s*Google Forms$", "", title).strip()

    if normalized_title != EXPECTED_TITLE:
        raise SystemExit(
            f'Expected form title "{EXPECTED_TITLE}", '
            f'but found "{title}".'
        )

    # Validate CSV columns
    check_columns(df, fields)

    print("CSV columns match the form.")
    print("Rows available:", len(df))

    post_url = clean_url(FORM_URL).replace(
        "/viewform", "/formResponse"
    )

    if DRY_RUN:
        print("\nDRY RUN: Nothing submitted.")
        print("Sample payload for row 1:")

        for key, value in build_payload(
            df.iloc[0], fields, pages
        )[:8]:
            print(f"  {key} = {value}")

        print("\nSet DRY_RUN = False only when you are ready.")
        return

    # Explicit confirmation before submission
    confirmation = input(
        f'Submit {len(df)} responses to "{EXPECTED_TITLE}"? '
        "Type YES: "
    )

    if confirmation != "YES":
        raise SystemExit("Cancelled.")

    submitted = 0

    with requests.Session() as session:
        for index, row in df.iterrows():
            payload = build_payload(row, fields, pages)

            try:
                response = session.post(
                    post_url,
                    data=payload,
                    timeout=30,
                )
                response.raise_for_status()

                submitted += 1
                print(f"Row {index + 1}: request sent")

            except requests.RequestException as error:
                print(f"Row {index + 1}: FAILED - {error}")
                break

            time.sleep(DELAY)

    print(f"\nFinished: {submitted}/{len(df)} requests sent.")
    print(
        "Note: HTTP success alone does not guarantee "
        "that Google Forms recorded every response."
    )


if __name__ == "__main__":
    main()







