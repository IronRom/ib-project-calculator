"""Quick extraction test. Run inside backend container:
  docker exec ib-project-calculator-backend-1 python3 -m app.scripts.test_extraction <path>
"""
import asyncio
import sys
import json

def _read_docx(path: str) -> str:
    try:
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        return f"[docx error: {e}]"

async def main(path: str):
    from app.database import SessionLocal
    from app.services.entity_extractor import extract_entities

    text = _read_docx(path)
    print(f"TZ length: {len(text)} chars\n")

    db = SessionLocal()
    try:
        result = await extract_entities(text, db)
    finally:
        db.close()

    print(f"Stage: {result.stage}")
    print(f"Region: {result.region}")
    print(f"Confidence: {result.overall_confidence}")
    print(f"Missing: {result.missing_data}")
    print(f"\nEntities ({len(result.entities)}):")
    for i, e in enumerate(result.entities):
        coeffs = [f"{c.name}(×?)" for c in e.coefficients]
        print(f"  [{i}] {e.object_name}")
        print(f"       table={e.sbts_table}  X={e.x_value} {e.x_unit}  qty={e.quantity}  conf={e.confidence:.2f}")
        if coeffs:
            print(f"       coefficients: {', '.join(coeffs)}")
        if e.notes:
            print(f"       notes: {e.notes[:120]}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python3 -m app.scripts.test_extraction <path_to_docx>")
        sys.exit(1)
    asyncio.run(main(path))
