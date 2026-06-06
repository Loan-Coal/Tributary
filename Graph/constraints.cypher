CREATE CONSTRAINT entity_id     IF NOT EXISTS FOR (e:Entity)       REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT account_id    IF NOT EXISTS FOR (a:Account)      REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT txn_id        IF NOT EXISTS FOR (t:Transaction)  REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT cp_id         IF NOT EXISTS FOR (c:Counterparty) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT jur_id        IF NOT EXISTS FOR (j:Jurisdiction) REQUIRE j.id IS UNIQUE;
CREATE CONSTRAINT obl_id        IF NOT EXISTS FOR (o:Obligation)   REQUIRE o.id IS UNIQUE;

CREATE INDEX txn_date    IF NOT EXISTS FOR (t:Transaction) ON (t.date);
CREATE INDEX txn_account IF NOT EXISTS FOR (t:Transaction) ON (t.account_id);
CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity)      ON (e.type);