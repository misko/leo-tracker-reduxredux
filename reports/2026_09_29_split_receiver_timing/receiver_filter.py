"""Partition already validated documents by software receiver, preserving records."""


def receiver_documents(documents, receiver):
    receiver = str(receiver)
    if receiver not in ("0", "1"):
        raise ValueError("Unknown requested software receiver")
    result = []
    for document in documents:
        tracks = document["tracks"]
        labels = {str(track["receiver_id"]) for track in tracks}
        if labels != {"0", "1"}:
            raise ValueError("Each recording must contain both and only the two receivers")
        if len({track["track_id"] for track in tracks}) != len(tracks):
            raise ValueError("Duplicate track identity")
        selected = [track for track in tracks if str(track["receiver_id"]) == receiver]
        result.append({**document, "tracks": selected})
    return result
