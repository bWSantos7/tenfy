# COSAT — Pipeline via n8n (OBSOLETO)

> **ATENÇÃO: Este documento está obsoleto e não representa o fluxo oficial.**
>
> COSAT **não usa n8n**. O n8n é utilizado apenas para CBT e FBT.
>
> O fluxo oficial COSAT é exclusivamente:
>
> ```
> MongoDB do crawler (bWSantos7/crawler.git)
>   → python manage.py sync_cosat_from_mongo --no-dry-run
>     → PostgreSQL (TournamentEdition + FederationEntry)
>       → API / App
> ```
>
> **Documentação correta:** [cosat_mongo_sync.md](cosat_mongo_sync.md)

---

*Arquivo mantido apenas para rastreabilidade histórica. Não implementar este pipeline.*
