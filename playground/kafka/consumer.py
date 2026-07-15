from kafka import KafkaConsumer
import json

consumer=KafkaConsumer(
    "hivemind.events",
    bootstrap_servers="localhost:9092",
    auto_offset_reset="earliest",
    value_deserializer=lambda m: json.loads(m.decode("utf-8"))
)

print("Wating for events...\n")

for m in consumer:
    print(m.value)

    