# HW8 Results and Metrics

## Configuration

| Value | Result |
|---|---:|
| SID4 | 2974 |
| PORT_BASE | 8274 |
| PREFIX | `s2974` |
| SEED | 2974 |
| VERIFY_SEED | 262974 |
| DOMAIN_ID | 6 |
| Local model | `qwen3:8b` |

## Part 1 - Kafka Request/Response

| Check | Result |
|---|---|
| FastAPI port | `8274` |
| Request topic | `s2974_entity_requests` (1 partition) |
| Response topic | `s2974_entity_responses` (1 partition) |
| `CREATE_LISTING` followed by `GET_LISTING` | PASS |
| Correlation ID preserved through Kafka | PASS |
| Invalid requests return clean error messages | PASS |

## Part 2 - Three-Agent Pipeline

| Stage | Input topic | Output topic |
|---|---|---|
| Planner | `s2974_inbox` | `s2974_tasks` |
| Writer | `s2974_tasks` (2 partitions) | `s2974_drafts` |
| Reviewer | `s2974_drafts` | `s2974_final` |

The recorded end-to-end message preserved one correlation ID across all three
agents and ended with `status: approved`. Each agent ran as an independent
process and committed its consumed Kafka offset only after publishing its
output.

## Part 3 - Failure Behavior

| Failure scenario | Before fix / failure evidence | After fix / recovery evidence |
|---|---|---|
| Duplicate delivery | Replaying one `correlation_id` created two different entity IDs; `extra_side_effect=true`. | The idempotency cache returned the first response and entity ID; `idempotent_replay=true` and `extra_side_effect=false`. |
| Consumer killed mid-work | Writer was killed after receiving partition 1, offset 0 and before committing; the container exited 137. | After restart, Writer received partition 1, offset 0 again, completed it, committed it, and produced an approved final message. |
| Poison message | Without a bounded failure path, `ValueError: plan is required` could prevent the task offset from advancing. | Writer attempted the message 3 times, moved it to `s2974_dead_letter`, committed the source offset, and the later valid message completed with `status: approved`. |
| Two partitions / two consumers | With no entity key, 20 related messages used partitions 0 and 1 and two Writers; global order was not preserved. | With key `property-6-262974`, all 20 messages used partition 0 and were processed in sequence 1-20. |

### Recorded failure metrics

| Metric | Result |
|---|---:|
| Duplicate side effects before fix | 2 entities from 1 replayed request |
| Duplicate side effects after fix | 1 entity; cached response reused |
| Consumer-death processing delay | 60 seconds |
| Consumer-death redelivery | Same partition 1, offset 0 |
| Poison-message maximum attempts | 3 |
| Later message after poison task | PASS |
| Ordering messages per run | 20 |
| No-key partitions / Writers used | 2 / 2 |
| No-key global order preserved | No |
| Entity-key partitions used | 1 |
| Entity-key global order preserved | Yes |

## HW2 In-Process Graph vs. Kafka

### Two benefits gained

1. **Independent scaling:** Planner, Writer, and Reviewer are separate
   consumers, so a slow stage can be replicated without duplicating the whole
   application.
2. **Decoupled failure and recovery:** Kafka retains uncommitted messages, so a
   restarted consumer can resume work instead of losing the request with the
   failed process.

### Two new responsibilities

1. **Duplicate delivery and idempotency:** At-least-once delivery can repeat a
   message, so side effects must be keyed and cached safely.
2. **Ordering, retries, and offset control:** The application must choose
   partition keys, bound retries, route poison messages to a DLQ, and commit
   offsets only after the desired outcome is durable.
