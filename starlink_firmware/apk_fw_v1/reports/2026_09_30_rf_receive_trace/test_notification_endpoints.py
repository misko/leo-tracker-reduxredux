from notification_endpoints import run


def test_notification_handle_table_matches_sender_indexing():
    assert len(run()['cases']) == 12
