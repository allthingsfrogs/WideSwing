#! /usr/bin/env python

import logging
import sys
import requests
import json

from fastapi import FastAPI
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.serialization import StringSerializer
from confluent_kafka import SerializingProducer
from config import config
from confluent_kafka.schema_registry.avro import AvroSerializer


from typing import Final



# send message to user, give choice of VCT region
# Americas, EMEA, APAC, CN
def region_selection():
    region = input("Enter region of the match you want to follow:")
    return region


#retrieve live match data including teams, map score, map count, top frags  
def fetch_live_match_data():
    response = requests.get("https://vlrggapi.vercel.app/match?q=upcoming")
    
    payload = json.loads(response.text)
    logging.debug("GOT %s", payload)
    return payload

# send message to user with live match summary
def live_summary(fetch_live_match_data):
    return {
        "team1": "Team A",
        "team2": "Team B",
        "map_score": "13-11",
        "map_count": 3
    }


def main():
    match_region = region_selection()
    #logging.info("GOT %s", match_region)
    r = fetch_live_match_data()
    print("Live Match Data:", r)

if __name__ == "__main__":    
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())

