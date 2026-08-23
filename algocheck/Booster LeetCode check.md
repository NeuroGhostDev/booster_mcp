# Booster + Nemotron 4B: LeetCode Validation

## Executive Summary

This is a small, reproducible product demo of Booster Home and the Booster
Cognitive Runtime running with `nvidia/nemotron-3-nano-4b` in LM Studio.

The point is not to claim that one model suddenly becomes perfect. The point is
to show the workflow difference:

```text
raw prompt -> plausible code -> hidden edge-case failure

Booster context + verification loop
  -> constraints stay visible
  -> failure is exposed
  -> reasoning is repaired
  -> accepted submission
```

Observed outcomes in this run:

| Problem | Initial signal | Booster-assisted result |
| --- | --- | --- |
| [10. Regular Expression Matching](https://leetcode.com/problems/regular-expression-matching/) | Wrong Answer on hidden cases | `354/354` accepted |
| [689. Maximum Sum of 3 Non-Overlapping Subarrays](https://leetcode.com/problems/maximum-sum-of-3-non-overlapping-subarrays/) | Wrong tie-breaking result | `43/43` accepted |
| [123. Best Time to Buy and Sell Stock III](https://leetcode.com/problems/best-time-to-buy-and-sell-stock-iii/) | Fresh hard DP task | `214/214` accepted |

The screenshots are evidence from an exploratory manual run, not a controlled
benchmark. Hardware, decoding parameters, prompt history, and model state were
not held constant across every attempt.

## Runtime Setup

- Model: `nvidia/nemotron-3-nano-4b`
- Backend: LM Studio OpenAI-compatible API
- Booster Home endpoint: `http://127.0.0.1:1234/v1`
- Problem language: Python 3
- Workflow: problem statement -> model solution -> local checks -> LeetCode
  submission -> failure analysis -> repaired solution -> resubmission

Launch command:

```bash
booster home \
  --base-url http://127.0.0.1:1234/v1 \
  --model nvidia/nemotron-3-nano-4b \
  --api-key lm-studio \
  --project .
```

Booster preserves Nemotron's provider-specific `reasoning_content`. When the
output budget is too small, Nemotron can spend the budget on reasoning and leave
`message.content` empty with `finish_reason=length`; that is reported as an
incomplete response instead of being presented as a successful answer.

## Case 1: Regular Expression Matching

The task is LeetCode Hard problem 10. The implementation must support `.` and
`*`, match the entire string, and handle patterns such as `a*`, `.*`, and
`mis*is*p*.`.

### Baseline: plausible code, hidden failure

The first generated dynamic-programming implementation looked reasonable and
passed a visible case, but the LeetCode result was Wrong Answer. The failing
cases exposed that a locally plausible explanation is not the same as a
validated algorithm.

![Baseline regular-expression attempt with hidden-case failure](Pasted%20image%2020260819181509.png)

### Booster-assisted repair

With the Booster workflow, the constraints, recurrence, empty-prefix handling,
and `*` transition stayed explicit. The agent iterated on the failure instead of
stopping at the first plausible implementation.

![Nemotron reasoning workspace with Booster context](Pasted%20image%2020260819182054.png)

The repaired implementation passed the full LeetCode test set:

![Regular-expression solution accepted with 354 of 354 test cases](Pasted%20image%2020260819182919.png)

The recorded result shows `354/354` test cases accepted, `4 ms` runtime, and
performance above the displayed runtime and memory percentiles.

Additional evidence from the same progression:

![Intermediate accepted regular-expression submission](Pasted%20image%2020260819182616.png)

![Nemotron local reasoning output before the repair loop](Pasted%20image%2020260819181419.png)

## Case 2: Maximum Sum of Three Non-Overlapping Subarrays

The second task is LeetCode Hard problem 689. It requires three non-overlapping
windows with maximum total sum and lexicographically smallest indices on ties.

### Failure that matters

The first long solution was mathematically detailed, but a hidden tie case still
produced `[0, 2, 7]` instead of the required `[0, 2, 4]`.

![Hidden tie-breaking failure on the first subarray solution](Pasted%20image%2020260819184401.png)

This is exactly the kind of failure that a context-and-validation workflow is
meant to surface: the proof narrative looked convincing, but the executable
behavior disagreed with the specification.

### Repaired result

After the new context pass and repair, the submission passed all `43/43` test
cases.

![Repaired subarray solution accepted with 43 of 43 test cases](Pasted%20image%2020260819185035.png)

The final visible result reports `36 ms` runtime and a valid lexicographically
smallest answer for the sample.

## Case 3: Best Time to Buy and Sell Stock III

The third task is LeetCode Hard problem 123. It requires at most two transactions
and is a useful check that the workflow generalizes beyond one recurrence.

![Stock III problem before solution generation](Pasted%20image%2020260819183155.png)

The resulting dynamic-programming solution passed `214/214` test cases.

![Stock III solution accepted with 214 of 214 test cases](Pasted%20image%2020260819183812.png)

The displayed submission reports `170 ms` runtime. This is an observed result
from one local run, not a universal performance guarantee.

## What the Demo Proves

The value is the loop, not a magic prompt:

1. Keep the task statement and constraints in context.
2. Generate a complete implementation instead of only a hint.
3. Run visible and hidden tests in the target judge.
4. Treat Wrong Answer as evidence, not as a prompt-writing problem.
5. Preserve the failure, inspect the algorithm, and repair the same slice.
6. Resubmit and retain the accepted evidence.

Booster contributes the context compiler, repository/world-model integration,
session memory, provider-compatible gateway, and an engineering workflow that
makes this loop repeatable.

## Full Evidence Gallery

### Regular Expression Matching

![LeetCode problem and first generated solution](Pasted%20image%2020260819180909.png)

![Nemotron local reasoning output with the engineering prompt](Pasted%20image%2020260819182054.png)

![Wrong Answer after an incomplete repair](Pasted%20image%2020260819182748.png)

![Accepted regular-expression result](Pasted%20image%2020260819182616.png)

### Maximum Sum of Three Subarrays

![Problem statement before implementation](Pasted%20image%2020260819184059.png)

![Long-form reasoning and implementation](Pasted%20image%2020260819182054.png)

![Accepted final subarray result](Pasted%20image%2020260819185035.png)

## Reproduction Checklist

1. Start LM Studio with `nvidia/nemotron-3-nano-4b` and enable its OpenAI API.
2. Verify `GET http://127.0.0.1:1234/v1/models` returns the configured model ID.
3. Start Booster Home with the command above.
4. Run the same problem statement through a fresh session.
5. Keep the first result and judge status as the baseline.
6. Run the repair pass with Booster context and submit again.
7. Record the exact test count, runtime, memory, model ID, and decoding settings.

For a production evaluation, repeat each arm with fixed seeds, temperature,
context, model state, and hardware. This folder is a product evidence case
study, not a statistically controlled model benchmark.
