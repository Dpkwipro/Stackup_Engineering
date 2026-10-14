"""Send January events, forward Critical escalations and save a summary (Task 3.2)."""

from pathlib import Path
from datetime import datetime, timezone
import json
import logging
import time
import uuid
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

ROOT = Path(__file__).resolve().parents[4]
EVENTS_FILE = ROOT / "datasets/events_stream/events_2025_01.jsonl"
OUT = ROOT / "outputs/results/deepak_shinghal/03_big_data/kafka"

KAFKA_SERVER = "localhost:9092"
SEND_DELAY = 0.05
TOPIC_EVENTS = "presight.project.events"
TOPIC_CRITICAL = "presight.escalations.critical"
LOG = logging.getLogger(__name__)


def encode_message(value):
    json_text = json.dumps(value)
    return json_text.encode("utf-8")


def decode_message(value):
    json_text = value.decode("utf-8")
    return json.loads(json_text)


def encode_key(key):
    return key.encode("utf-8")


def create_topics(bootstrap):
    admin = KafkaAdminClient(
        bootstrap_servers=bootstrap, client_id="presight-assessment-admin"
    )
    required = {TOPIC_EVENTS: 3, TOPIC_CRITICAL: 1}
    try:
        existing = admin.list_topics()
        for name, partition_count in required.items():
            if name not in existing:
                try:
                    admin.create_topics(
                        [
                            NewTopic(
                                name,
                                num_partitions=partition_count,
                                replication_factor=1,
                            )
                        ]
                    )
                except TopicAlreadyExistsError:
                    pass  # A concurrent process may have created it already.
        # Newly created topics may take a moment to appear in broker metadata.
        for attempt in range(40):
            metadata = admin.describe_topics(list(required))
            partition_counts = {}
            for topic in metadata:
                # Newer Kafka responses use "name"; older ones use "topic".
                topic_name = topic.get("name", topic.get("topic"))
                if topic.get("error_code", 0) == 0 and topic_name in required:
                    partition_counts[topic_name] = len(topic["partitions"])
            if partition_counts == required:
                return partition_counts
            time.sleep(0.25)
        raise ValueError(
            "Required topics did not become ready with correct partition counts"
        )
    finally:
        admin.close()


def build_producer(bootstrap):
    return KafkaProducer(
        bootstrap_servers=bootstrap,
        value_serializer=encode_message,
        key_serializer=encode_key,
        acks="all",
        retries=3,
        request_timeout_ms=30000,
    )


def run_producer(producer, events_file, run_id, delay_seconds=0.05):
    sent = 0
    start = time.perf_counter()
    with open(events_file, encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue

            event = json.loads(line)
            event["produced_at"] = datetime.now(timezone.utc).isoformat()
            event["run_id"] = run_id

            send_result = producer.send(
                TOPIC_EVENTS, key=event["event_type"], value=event
            )
            send_result.get(timeout=30)  # Wait for Kafka to confirm receipt.
            sent += 1
            if sent % 100 == 0:
                LOG.info("Produced %d events", sent)
            time.sleep(delay_seconds)
    producer.flush()
    result = {
        "run_id": run_id,
        "sent_count": sent,
        "delay_seconds": delay_seconds,
        "execution_seconds": time.perf_counter() - start,
    }
    LOG.info("Producer finished: %d events", sent)
    return result


def build_consumer(bootstrap, topic, run_id):
    # Fresh group per run avoids consuming only uncommitted remnants of another run.
    return KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id="presight-assessment-" + run_id,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=decode_message,
        consumer_timeout_ms=30000,
        max_poll_records=100,
    )


def is_critical(event):
    payload = event.get("payload") or {}
    if event.get("event_type") != "escalation_raised":
        return False
    return payload.get("severity") == "Critical"


def run_consumer(consumer, producer, run_id, expected_count):
    start = time.perf_counter()
    counts = {}
    consumed = 0
    forwarded = 0

    messages = []
    if expected_count > 0:
        messages = consumer
    for message in messages:
        event = message.value
        if event.get("run_id") != run_id:
            continue  # Skip prior runs without deleting any broker data.

        event_type = event["event_type"]
        if event_type not in counts:
            counts[event_type] = 0
        counts[event_type] += 1
        consumed += 1

        if is_critical(event):
            send_result = producer.send(
                TOPIC_CRITICAL, key=event["event_type"], value=event
            )
            send_result.get(timeout=30)  # Count forwarding only after confirmation.
            forwarded += 1
        if consumed % 100 == 0:
            # Commit only after the messages' side effects are acknowledged.
            consumer.commit()
            LOG.info("Consumed %d; Critical forwarded %d", consumed, forwarded)
        if consumed >= expected_count:
            break
    producer.flush()
    consumer.commit()
    LOG.info(
        "Consumer finished: %d events; Critical forwarded: %d", consumed, forwarded
    )
    if consumed != expected_count:
        raise ValueError("Consumer stopped before expected count: " + str(consumed))
    # Avoid division by zero for a very fast/empty run.
    elapsed = max(time.perf_counter() - start, 0.000001)

    result = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "total_messages_consumed": consumed,
        "count_per_event_type": counts,
        "critical_escalations_forwarded": forwarded,
        "execution_seconds": elapsed,
        "throughput_messages_per_second": consumed / elapsed,
        "throughput_scope": "consumer processing only; producer delay is reported separately",
    }
    return result


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    # A unique label keeps this run's events separate from earlier runs.
    run_id = uuid.uuid4().hex
    LOG.info("Run ID: %s", run_id)

    partitions = create_topics(KAFKA_SERVER)
    producer = build_producer(KAFKA_SERVER)
    try:

        produced = run_producer(producer, EVENTS_FILE, run_id, SEND_DELAY)

        consumer = build_consumer(KAFKA_SERVER, TOPIC_EVENTS, run_id)
        try:
            result = run_consumer(consumer, producer, run_id, produced["sent_count"])
        finally:
            consumer.close()

        result["topic_partitions"] = partitions
        result["producer"] = produced
        OUT.mkdir(parents=True, exist_ok=True)
        summary_path = OUT / "summary.json"
        json_text = json.dumps(result, indent=2)
        summary_path.write_text(json_text + "\n")
        LOG.info("Kafka summary: %s", result)
    finally:
        producer.close()


if __name__ == "__main__":
    main()
