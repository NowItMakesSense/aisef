-- 0041: tabela de assinaturas
ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'trial';
