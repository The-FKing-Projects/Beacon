# Confidence Scoring Design

## Purpose

Beacon should explain why software was classified in a particular way.

Confidence scoring allows Beacon to communicate certainty and uncertainty.

---

## Example

```text
Steam
Source: Repository
Confidence: High
```

```text
Discord PTB
Source: Local .deb Candidate
Confidence: Medium
```

---

## Potential Signals

### Repository URL Found

```text
Strong evidence
```

---

### Homepage Present

```text
Weak evidence
```

---

### Maintainer Present

```text
Weak evidence
```

---

### Upstream Match Found

```text
Strong evidence
```

---

## Possible Output

```text
High
Medium
Low
```

Or:

```text
0-100
```

---

## Open Questions

- Numeric or descriptive scoring?
- User visible or internal?
- Thresholds for classification?

---

## Related Issues

- #8 Design confidence scoring system
- #12 Design package provenance confidence scoring
