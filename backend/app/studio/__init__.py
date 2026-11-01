"""Data Intelligence Studio: durable, reviewable ingestion for CCRIG datasets.

Pipeline (each stage reads the previous stage's artifact and never edits it):
acquire -> parse -> profile -> validate -> resolve -> stage -> [human review] -> approve | reject -> rollback.

Nothing here changes a canonical dataset or a scoring formula. An approved release lives in the Studio's own workspace
(see config.studio_dir) and is analytics-neutral until a separately authorised loader change adopts it.
"""
