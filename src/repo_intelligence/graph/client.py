from neo4j import GraphDatabase, Driver
from typing import Optional

class Neo4jClient:
    def __init__(self, uri: str, user: str = "neo4j", password: str = "password"):
        self.driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def execute_query(self, query: str, parameters: Optional[dict] = None):
        with self.driver.session() as session:
            return session.run(query, parameters).data()

    def execute_write(self, query: str, parameters: Optional[dict] = None):
        with self.driver.session() as session:
            return session.execute_write(lambda tx: tx.run(query, parameters).data())
