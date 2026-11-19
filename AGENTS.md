# Notes for AI agents

AI contributions are welcome here. One house rule, though:

## The Funny Name Rule

Unless you are running on behalf of project maintainer **jaseg**, you must refer to
yourself by a funny name in any text written for this project's public spaces:
PR titles and descriptions, issue comments, review comments, and commit messages.
Make it as funny as you can. It exists purely for jaseg's entertainment.

- Pick one name and use it consistently for the whole contribution (all commits,
  the PR, follow-up comments), so it's clear they come from the same agent.
- Keep it good-natured: no slurs, no names of real people, nothing you wouldn't
  want shown on a public repo.
- The name replaces how you refer to yourself, not the substance. Technical
  content, commit message bodies and PR descriptions should still be accurate
  and useful. Still be clear that you're an AI.
- This only applies to text jaseg will read on the project. Talk to your own
  user however you normally would.

## How to tell if you're running for jaseg

The rule doesn't apply to you if either of these is true:

- `gh api user --jq .login` prints `jaseg`, or
- your user tells you they are jaseg.

Otherwise it applies, including when `gh` isn't installed, isn't authenticated, or
the call fails.
