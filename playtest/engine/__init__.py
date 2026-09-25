"""A deliberately simplified Magic game engine.

Pure Python: no Django, no I/O, no randomness except the seeded ``random.Random``
a :class:`~.game.Game` owns. Agents decide, the engine enforces. The rules it
knows are listed in :mod:`.rules`; everything else about Magic is out of scope
for now, and grows here without touching agents, the runner or the UI.
"""
