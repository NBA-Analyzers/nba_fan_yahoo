"""Tiny in-memory stand-in for the Firestore client calls the user-data code makes."""


class FakeSnap:
    def __init__(self, ref, data):
        self.reference, self._data = ref, data
        self.exists = data is not None
        self.create_time = None

    def to_dict(self):
        return dict(self._data)


class FakeDoc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def _check(self):
        if self.db.fail_writes:
            raise RuntimeError("firestore unavailable")

    def set(self, data, merge=False):
        self._check()
        self.db.writes += 1
        if merge and self.path in self.db.data:
            self.db.data[self.path].update(data)
        else:
            self.db.data[self.path] = dict(data)

    def create(self, data):
        from google.api_core.exceptions import AlreadyExists

        self._check()
        if self.path in self.db.data:
            raise AlreadyExists(self.path)
        self.db.writes += 1
        self.db.data[self.path] = dict(data)

    def update(self, data):
        self._check()
        if self.path not in self.db.data:
            raise KeyError(self.path)
        self.db.data[self.path].update(data)

    def get(self):
        return FakeSnap(self, self.db.data.get(self.path))

    def delete(self):
        self.db.data.pop(self.path, None)


class FakeQuery:
    def __init__(self, db, name, filters=(), limit=None):
        self.db, self.name, self.filters, self._limit = db, name, tuple(filters), limit

    def where(self, field, op, value):
        assert op == "=="
        return FakeQuery(self.db, self.name, self.filters + ((field, value),), self._limit)

    def limit(self, n):
        return FakeQuery(self.db, self.name, self.filters, n)

    def stream(self):
        prefix = self.name + "/"
        out = []
        for path, data in self.db.data.items():
            if path.startswith(prefix) and all(data.get(f) == v for f, v in self.filters):
                out.append(FakeSnap(FakeDoc(self.db, path), data))
        return out[: self._limit] if self._limit else out


class FakeCollection(FakeQuery):
    def document(self, doc_id):
        return FakeDoc(self.db, f"{self.name}/{doc_id}")


class FakeFirestore:
    def __init__(self):
        self.data = {}
        self.writes = 0
        self.fail_writes = False

    def collection(self, name):
        return FakeCollection(self, name)

    def docs(self, name):
        prefix = name + "/"
        return {p[len(prefix):]: d for p, d in self.data.items() if p.startswith(prefix)}
