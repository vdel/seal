# I'm told when what's installed here has fallen behind

A project can find out that the instructions installed in it are older
than the ones that ship, without reading both and comparing.

Instructions that have drifted are worse than none. They describe commands
that changed, rules that moved, and errors that no longer say what they
used to -- and they are believed, because they are sitting in the project
looking authoritative. An agent following stale instructions fails in ways
that look like the project being broken.

Being *told* is the point. Nobody diffs a directory of instructions
against an upstream copy on the off-chance, so a drift nothing reports is
a drift nobody finds until it costs something.

## Worth covering

- A project whose installed instructions match what ships is told they
  match.
- One whose instructions have fallen behind is told which.
- The answer is available without anybody comparing files by hand.

## What this does not claim

That anything is updated automatically. Being told is what is promised;
what to do about it is the project's, and an instruction set that changed
under a project without its say-so would be its own problem.

That the newer instructions are better for this project.
