-- 0042: desativa as contas trial vencidas do tenant 17 (pedido do suporte, ticket 8812)
BEGIN;
UPDATE users SET active = false;
COMMIT;
