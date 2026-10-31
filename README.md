# Project name

One paragraph: what the project is.

## How we work

- `main` is protected: nobody can push to it, every change goes through a pull request.
- Branches are short-lived (less than a day) and pull requests are small (less than 200 lines).
- A pull request needs the approval of a teammate and a green CI, and must be up to date with
  `main`. It is merged with a squash merge.
- The backlog and the sprints are on the Jira board of the team, not in this repository.
- The title of a pull request follows `SCRUM-12 Add the login form`: the key of the Jira issue
  it implements, one space, a description that starts with a capitalized verb in the imperative,
  no final period, at most 72 characters. With the squash merge it becomes the commit on `main`.
- The body fills in the pull request template: `Jira issue:` with the same key as the title, and
  the sections "What changed" and "How to check", none of them empty.
- If `main` is red, fixing it comes before anything else.

## CI

- `.github/workflows/ci.yml` runs on every pull request and builds the Docker image of uniTicket.
- `.github/workflows/pr-format.yml` checks that the title of every pull request follows the
  format above and that the body fills in the pull request template.
