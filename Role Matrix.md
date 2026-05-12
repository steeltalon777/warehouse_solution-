# Role Matrix

## Roles
- root
- chief_storekeeper
- storekeeper
- observer

## Permissions

| Action                     | root | chief | storekeeper                  | observer |
|---------------------------|------|-------|------------------------------|----------|
| View data                 | YES  | YES   | YES                          | YES      |
| Create operations         | YES  | YES   | YES (allowed scope only)     | NO       |
| Submit operations         | YES  | YES   | NO or limited by rules       | NO       |
| Cancel operations         | YES  | YES   | own draft only               | NO       |
| Accept incoming goods     | YES  | YES   | YES (destination site only)  | NO       |
| Manage catalog            | YES  | YES   | NO                           | NO       |
| Manage users              | YES  | NO    | NO                           | NO       |