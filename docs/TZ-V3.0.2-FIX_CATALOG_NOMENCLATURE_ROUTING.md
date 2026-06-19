# TZ: V3.0.2 — Fix catalog/nomenclature routing: both show readonly

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Fix catalog-write.guard.ts — async auth load
- [x] 2. Verify on dev stand: `/catalog/` → readonly, `/nomenclature/` → editable (admin)
- [x] 3. Verify on dev stand: storekeeper → `/nomenclature/` redirects to `/catalog/`
- [x] 4. Angular build
- [x] 5. Documentation updated (no external docs needed — fix is internal to guard logic)
- [ ] 6. Final acceptance review

## Problem

В боковой панели «Каталог» (`/catalog/`) и «Номенклатура» (`/nomenclature/`) открывают один и тот же Angular SPA — read-only версию каталога.

**Root cause:** race condition в `catalog-write.guard.ts`.

`AuthContextService.authContext()` — Angular signal, `null` по умолчанию.  
`AuthContextService.load()` — асинхронный вызов BFF `/auth/me`. Вызывается в конструкторе `OperationsService`, но НЕ гарантированно до активации guard'а.

Guard — синхронный `CanActivateFn`:
```typescript
const role = auth.authContext()?.role;  // → undefined (authContext ещё null)
if (role === 'root' || role === 'chief_storekeeper') return true;
return router.createUrlTree(['/catalog']);  // ← всех редиректит на /catalog
```

## Fix

### Файл: `Warehouse_frontend/src/app/core/guards/catalog-write.guard.ts`

Заменить:

```typescript
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthContextService } from '../services/auth-context.service';

export const catalogWriteGuard: CanActivateFn = () => {
  const auth = inject(AuthContextService);
  const router = inject(Router);
  const role = auth.authContext()?.role;
  if (role === 'root' || role === 'chief_storekeeper') return true;
  return router.createUrlTree(['/catalog']);
};
```

На:

```typescript
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthContextService } from '../services/auth-context.service';

export const catalogWriteGuard: CanActivateFn = async () => {
  const auth = inject(AuthContextService);
  const router = inject(Router);

  // Ensure auth context is loaded before checking role.
  // load() is called elsewhere (e.g. OperationsService constructor) but
  // may not have completed by the time the guard runs on direct navigation.
  if (!auth.authContext()) {
    await auth.load();
  }

  const role = auth.authContext()?.role;
  if (role === 'root' || role === 'chief_storekeeper') return true;
  return router.createUrlTree(['/catalog']);
};
```

## Verification

### 1. Admin (root) — `/nomenclature/` должен открыть editable SPA

```bash
# Залогиниться admin/admin123 на dev-стенде
# Перейти на http://localhost:8001/nomenclature/
# Ожидается:
#   - URL остаётся /nomenclature/ (НЕ редиректит на /catalog)
#   - Заголовок «Номенклатура»
#   - Кнопки «Добавить», «Сохранить изменения» видны
```

### 2. Admin — `/catalog/` должен открыть readonly SPA

```bash
# Перейти на http://localhost:8001/catalog/
# Ожидается:
#   - Заголовок «Каталог»
#   - Подзаголовок «Просмотр категорий, ТМЦ, единиц измерения и ключевых слов»
#   - Нет кнопок редактирования
```

### 3. Storekeeper — `/nomenclature/` должен редиректить на `/catalog/`

```bash
# Залогиниться под storekeeper (не root/chief_storekeeper)
# Перейти на http://localhost:8001/nomenclature/
# Ожидается:
#   - Редирект на /catalog/
#   - Пункт «Номенклатура» в боковой панели скрыт
```

## Build

```bash
cd Warehouse_frontend
npm run build
```

## Out of Scope

- Изменения в Django views/templates/sidebar
- Изменения в Angular routing (роуты правильные, проблема только в guard)

## Assumptions

| Assumption | Status |
|---|---|
| `AuthContextService.load()` отрабатывает < 500ms на dev-стенде | Reasonable |
| BFF `/auth/me` возвращает корректную роль для всех типов пользователей | Validated |
