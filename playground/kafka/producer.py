from kafka import KafkaProducer
import json
import time

producer=KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

event={
    "event":"hello",
    "message":"Hello Hivemind!"
}
producer.send("hivemind.events",event)
producer.flush()

print("Event plubished succesfully")
