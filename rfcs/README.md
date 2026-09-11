# RFCs

The design record. One document per decision area: what was decided, why,
what it costs, and what was considered instead.

These pages are for somebody **changing** Seal. They state the
reasoning a contract rests on, not how to use it -- if you are building a
project *on* Seal, [`/docs/`](../docs/) is the user manual and covers
every subject below as a task rather than as an argument.

The division is strict, and worth keeping that way:

| A page here answers | `/docs/` answers |
| --- | --- |
| why the rule is the rule | what the rule is, and how to satisfy it |
| what a design refuses to do, and why | what a command does |
| what was rejected, and what it would have cost | how to get a green run |

A claim in an RFC has to be something the CLI, the extensions or the checks
actually do. An RFC describing a capability Seal doesn't have is worse
than a missing RFC.

## The series

| # | Title | Subject |
| --- | --- | --- |
| [0001](0001-library-boundary.md) | The library boundary | What Seal is, and what it refuses to know |
| [0002](0002-declaration-by-structure.md) | Declaration by structure | Why there is no registry, and how discovery works without one |
| [0003](0003-readiness.md) | Readiness, and what a green run claims | Why `seal ci` refuses to start without a probe on every container |
| [0004](0004-deterministic-state.md) | Deterministic state | The reset contract, when it fires, and what makes seed data trustworthy |
| [0005](0005-service-tests.md) | Where a service's own tests run | In the deployed container, and why not in the build or the entrypoint |
| [0006](0006-credential-resolution.md) | Credentials: one schema, many stores | Why a `.env` names an item and the project names the store |
| [0007](0007-credential-delivery.md) | Credentials: the overlay owns the objects | Why the manifests name what carries a service's values into a pod |
| [0008](0008-run-axes.md) | What a run selects | The four axes a run states independently, and what publishing needs |
| [0009](0009-outcome-tests.md) | Outcome tests and unattended merge | The trust mechanism the whole project turns on |
| [0010](0010-outcome-tree.md) | The outcome tree | Why a promise and its translation share a directory |
| [0011](0011-outcome-runners.md) | Outcome runners | What runs a promise, and the contract every runner meets |
| [0012](0012-translation-and-review.md) | Translation and review | Why a translation needs a human, and what Seal does around it |
| [0013](0013-regression-loop.md) | The regression loop | How a red suite gets back to green without anybody editing a test |
| [0014](0014-seal-on-seal.md) | Seal homologates itself | What Seal promises, and the runner those promises need |
| [0015](0015-reporting-what-a-run-found.md) | Reporting what a run found | Who reads a verdict, who renders it, and who publishes it |

## Reading order

0001 and 0002 are the foundations every other page assumes. After those:

- **Bringing an environment up** -- 0003, 0004, 0005.
- **Credentials** -- 0006, then 0007. One path with two ends.
- **What a run selects** -- 0008.
- **The gate** -- 0009 first; it is the argument the rest of the outcome
  series serves. Then 0010 (the tree), 0011 (what runs it), 0012 (how a
  promise becomes a test), 0013 (what happens when one goes red).

0015 sits beside the gate: what a run establishes is 0009's, and how
anybody finds out is 0015's.

0014 reads last, and reads back over everything above it: it states what
Seal promises an adopting project, which is the whole series as
promises rather than as arguments, and decides the runner those promises
need.

## The format

Each RFC opens with a status table, then:

- **Context** -- the problem, stated without the solution in it.
- **Decision** -- what holds, in as few sentences as it takes.
- **Rationale** -- why, in sections. This is the body, and the reason the
  page exists.
- **Consequences** -- what the decision costs, including the costs accepted
  on purpose.
- **Alternatives considered** -- what else would have worked, and what each
  one lost on.
- **Open questions** -- what is genuinely undecided. Nothing that has an
  answer belongs here.

Statuses:

| Status | Means |
| --- | --- |
| **Accepted** | The decision holds and the code implements it. |
| **Accepted, partly implemented** | The decision holds; some of it is not built. The RFC says which part. |
| **Record** | A decision with nothing to implement. |

## Conventions

The repository's writing rules apply here (see [`/CLAUDE.md`](../CLAUDE.md)):
describe the current design and its rationale, never the journey that
reached it. An RFC records what was *considered and rejected* -- which is
rationale -- and not what this repository used to do, which is not.

Link to `/docs/` pages by relative path, and keep the how-to there. A
paragraph that starts explaining how to write a `.env` belongs on the other
side of the line.
