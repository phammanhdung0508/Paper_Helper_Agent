import timeit

setup = """
from collections import namedtuple
Message = namedtuple('Message', ['content', 'type'])
messages = [Message(content=f"msg_{i}", type="human") for i in range(1000)]

class State:
    def __init__(self, msgs):
        self.messages = msgs

state = State(messages)
"""

test_current = """
history_text = ""
for msg in state.messages[:-1]:
    sender = "User" if getattr(msg, "type", "") == "human" else "Assistant"
    content = getattr(msg, "content", str(msg))
    history_text += f"{sender}: {content}\\n"
"""

test_optimized = """
history_text = "".join(
    f"{'User' if getattr(msg, 'type', '') == 'human' else 'Assistant'}: {getattr(msg, 'content', str(msg))}\\n"
    for msg in state.messages[:-1]
)
"""

# Run timeit
time_current = timeit.timeit(stmt=test_current, setup=setup, number=10000)
time_optimized = timeit.timeit(stmt=test_optimized, setup=setup, number=10000)

print("--- Performance Baseline for Formatting History ---")
print(f"Current Loop + Concatenation (+=): {time_current:.5f} s")
print(f"Proposed join + generator comprehension: {time_optimized:.5f} s")
print(f"Improvement: {(time_current - time_optimized) / time_current * 100:.2f}% faster")
