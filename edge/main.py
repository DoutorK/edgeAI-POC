import argparse
import json
from pathlib import Path

from app.logger import configure_logging
from app.pipeline import process_document, save_structured_json, send_to_backend
from app.sync import sync_pending


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline edge para documentos jurídicos")
    parser.add_argument("--input", help="Caminho do PDF/imagem")
    parser.add_argument("--out", default="../data/structured_output.json", help="Arquivo JSON de saída")
    parser.add_argument("--offline", action="store_true", help="Executa apenas extração local")
    parser.add_argument("--sync-pending", action="store_true", help="Sincroniza payloads pendentes com backend")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    if args.sync_pending:
        result = sync_pending(Path("../data/pending_sync"))
        print(json.dumps({"mode": "sync", "result": result}, ensure_ascii=False, indent=2))
        return

    if not args.input:
        raise ValueError("Informe --input ou use --sync-pending.")

    file_path = Path(args.input)
    out_path = Path(args.out)

    structured = process_document(file_path)
    save_structured_json(structured, out_path)

    if args.offline:
        print(json.dumps({"mode": "offline", "structured_data": structured.to_dict()}, ensure_ascii=False, indent=2))
        return

    llm_analysis = send_to_backend(structured)
    print(json.dumps({"mode": "hybrid", "structured_data": structured.to_dict(), "analysis": llm_analysis}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
