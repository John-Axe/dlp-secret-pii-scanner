# Token format reference (internal notes, no real credentials)

Quick reference for what our secret-scanning tooling looks for. None of the
shapes described below are real tokens - just format descriptions used in
onboarding docs.

- AWS access keys start with the `AKIA` or `ASIA` prefix, followed by 16
  more uppercase letters and digits.
- Classic GitHub tokens start with `ghp_`, `gho_`, `ghu_`, `ghs_`, or `ghr_`.
- GitLab personal access tokens start with `glpat-`.
- Slack tokens start with `xoxb-` for bots or `xoxp-` for users.

If you see a string matching one of these shapes in a pull request, treat
it as a real leaked credential until proven otherwise.
