from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; run inside the app container or install psycopg[binary]") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    updated_positions = 0
    updated_documents = 0
    updated_evidence = 0
    samples: list[dict[str, Any]] = []

    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select p.item_id, p.payload, i.payload, s.payload, c.payload
                from ai_quant.records p
                join ai_quant.records s on s.collection='securities' and s.item_id=p.payload->>'security_id'
                join ai_quant.records i on i.collection='issuers' and i.item_id=p.payload->>'issuer_id'
                left join ai_quant.records c on c.collection='industry_chains' and c.item_id=p.payload->>'chain_id'
                where p.collection='company_positions'
                  and s.payload->>'market'='A'
                  and s.payload->>'company_universe_scope'='in_scope'
                order by s.payload->>'ticker'
                """
            )
            rows = cursor.fetchall()
            now = datetime.now(timezone.utc).isoformat()
            for position_id, position_payload, issuer_payload, security_payload, chain_payload in rows:
                position = dict(position_payload)
                issuer = dict(issuer_payload)
                security = dict(security_payload)
                chain = dict(chain_payload or {})
                symbol = str(security.get("ticker") or "")
                name = str(issuer.get("legal_name") or symbol)
                exchange = str(security.get("exchange") or "")
                chain_name = str(chain.get("name") or position.get("chain_id") or "A股产业链")
                node_ids = list(position.get("node_ids") or [])
                node_id = str(node_ids[0]) if node_ids else ""
                industry = str((position.get("revenue_exposure") or {}).get("industry") or "待补行业")
                if industry == "非公司类证券":
                    industry = "待补行业"

                position["role"] = f"{industry}公司的产业链节点参与者"
                position["positioning_summary"] = f"{name}（{symbol}）归入“{chain_name}”的“{node_id or '未细分节点'}”节点。"
                position["revenue_exposure"] = {
                    **dict(position.get("revenue_exposure") or {}),
                    "type": "directory_classification",
                    "industry": industry,
                    "company_name": name,
                    "ticker": symbol,
                }
                position["valuation_metrics"] = {
                    **dict(position.get("valuation_metrics") or {}),
                    "market": "A",
                    "currency": str(security.get("currency") or "CNY"),
                    "exchange": exchange,
                    "security_type": str(security.get("security_type") or "common_stock"),
                    "company_universe_scope": "in_scope",
                }
                position["event_refs"] = sorted(set(list(position.get("event_refs") or []) + [f"artifact://full-ahu-universe/A/{symbol}"]))
                cursor.execute(
                    """
                    insert into ai_quant.records (collection, item_id, payload, position)
                    values ('company_positions', %s, %s::jsonb, null)
                    on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                    """,
                    (position_id, json.dumps(position, ensure_ascii=False, sort_keys=True)),
                )
                updated_positions += 1

                document_id = f"doc_a_{symbol.lower()}_profile"
                evidence_id = f"evi_a_{symbol.lower()}_profile"
                body = "\n".join(
                    [
                        f"公司: {name} ({symbol})",
                        f"市场/交易所: A / {exchange}",
                        f"行业: {industry}",
                        f"产业链: {chain_name}",
                        f"产业链节点: {node_id or '未细分节点'}",
                        "使用边界: 公开目录、本地 TDX 日线目录和免费行情名称补充生成的基础资料，用于研究图谱和产业链覆盖，不构成交易指令。",
                    ]
                )
                cursor.execute("select payload from ai_quant.records where collection='documents' and item_id=%s", (document_id,))
                doc_row = cursor.fetchone()
                if doc_row:
                    document = dict(doc_row[0])
                    document["title"] = f"{symbol} {name} 基础资料与产业链定位"
                    document["body"] = body
                    document["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
                    document["source_uri"] = f"artifact://full-ahu-universe/A/{symbol}"
                    document["updated_at"] = now
                    cursor.execute(
                        """
                        insert into ai_quant.records (collection, item_id, payload, position)
                        values ('documents', %s, %s::jsonb, null)
                        on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                        """,
                        (document_id, json.dumps(document, ensure_ascii=False, sort_keys=True)),
                    )
                    updated_documents += 1
                cursor.execute("select payload from ai_quant.records where collection='evidence' and item_id=%s", (evidence_id,))
                evidence_row = cursor.fetchone()
                if evidence_row:
                    evidence = dict(evidence_row[0])
                    evidence["span_text"] = body
                    evidence["canonical_text"] = body
                    evidence["locator"] = {"type": "full_universe_directory", "market": "A", "symbol": symbol, "chain_id": position.get("chain_id"), "node_id": node_id}
                    evidence["assets"] = [{"issuer_id": position.get("issuer_id"), "security_id": position.get("security_id"), "ticker": symbol}]
                    cursor.execute(
                        """
                        insert into ai_quant.records (collection, item_id, payload, position)
                        values ('evidence', %s, %s::jsonb, null)
                        on conflict (collection, item_id) do update set payload=excluded.payload, updated_at=now()
                        """,
                        (evidence_id, json.dumps(evidence, ensure_ascii=False, sort_keys=True)),
                    )
                    updated_evidence += 1
                if len(samples) < 20:
                    samples.append({"symbol": symbol, "name": name, "exchange": exchange, "position_id": position_id})
            connection.commit()

    return {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "updated_positions": updated_positions,
        "updated_documents": updated_documents,
        "updated_evidence": updated_evidence,
        "samples": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync A-share company position cards with latest issuer/security directory fields.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--artifact", default="artifacts/ashare-company-position-sync.json")
    args = parser.parse_args()
    result = run(args)
    artifact = Path(args.artifact)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
