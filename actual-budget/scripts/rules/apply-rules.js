// Moteur générique de création de règles de catégorisation Actual Budget.
// Lit un fichier de règles déclaratif (JSON) et crée les règles correspondantes
// via l'API Actual. Réutilisable tel quel pour la production : seul le fichier
// de règles change (nouveaux payees réels), pas ce script. Voir README.md.
//
// Usage :
//   ACTUAL_SERVER_URL=http://127.0.0.1:8083 \
//   ACTUAL_PASSWORD=... \
//   ACTUAL_SYNC_ID=... \
//   node apply-rules.js rules.test.json
//
// Idempotent : une règle déjà présente (mêmes conditions + mêmes actions) n'est pas recréée.
// Ne s'applique qu'aux transactions futures (import/synchro) : pour recatégoriser les
// transactions déjà existantes au moment de la création des règles, voir categorize-existing.js.

const path = require('path');
const fs = require('fs');
const { api, buildCategoryIndex, resolveAccountId, requireCategory, requireEnv } = require('./lib');

async function main() {
  const rulesFile = process.argv[2];
  if (!rulesFile) {
    console.error('Usage: node apply-rules.js <rules-file.json>');
    process.exit(1);
  }

  const spec = JSON.parse(fs.readFileSync(rulesFile, 'utf8'));

  const serverURL = process.env.ACTUAL_SERVER_URL || 'http://127.0.0.1:8083';
  const password = requireEnv('ACTUAL_PASSWORD');
  const syncId = requireEnv('ACTUAL_SYNC_ID');

  await api.init({
    dataDir: path.join(__dirname, '.cache'),
    serverURL,
    password,
  });

  await api.downloadBudget(syncId);

  try {
    const categoryIdByPath = await buildCategoryIndex();
    const accountId = await resolveAccountId(spec.account);
    const existingSignatures = await buildExistingRuleSignatures();

    let created = 0;
    let skippedExisting = 0;
    const missingCategories = new Set();

    // 1. Catch-all "À vérifier" en premier, en stage 'pre' : les règles 'pre'
    // s'appliquent toujours avant les règles par défaut, donc toute règle
    // spécifique plus bas dans ce fichier écrasera cette catégorie par défaut
    // si elle matche. Les transactions qu'aucune règle spécifique ne couvre
    // restent ainsi visibles dans "À vérifier" plutôt que de disparaître en
    // "Uncategorized" (cf. plan-configuration.md §2.3).
    if (spec.catchAllCategory) {
      const catchAllCategoryId = requireCategory(categoryIdByPath, spec.catchAllCategory, missingCategories);
      if (catchAllCategoryId) {
        const rule = {
          stage: 'pre',
          conditionsOp: 'and',
          conditions: [{ field: 'account', op: 'is', value: accountId }],
          actions: [{ field: 'category', op: 'set', value: catchAllCategoryId }],
        };
        const result = await createRuleIfNew(rule, existingSignatures);
        created += result ? 1 : 0;
        skippedExisting += result ? 0 : 1;
      }
    }

    // 2. Règles spécifiques (stage par défaut = null), une règle par mot-clé.
    for (const entry of spec.rules) {
      const categoryId = requireCategory(categoryIdByPath, entry.category, missingCategories);
      if (!categoryId) continue;

      for (const keyword of entry.keywords) {
        const conditions = [{ field: entry.field || 'imported_payee', op: 'contains', value: keyword }];
        for (const excluded of entry.exclude || []) {
          conditions.push({ field: entry.field || 'imported_payee', op: 'doesNotContain', value: excluded });
        }
        const rule = {
          stage: null,
          conditionsOp: 'and',
          conditions,
          actions: [{ field: 'category', op: 'set', value: categoryId }],
        };
        const result = await createRuleIfNew(rule, existingSignatures);
        created += result ? 1 : 0;
        skippedExisting += result ? 0 : 1;
      }
    }

    console.log(`Règles créées : ${created}`);
    console.log(`Règles déjà présentes (ignorées) : ${skippedExisting}`);
    if (missingCategories.size > 0) {
      console.log('Catégories introuvables (règles ignorées pour ces entrées) :');
      for (const c of missingCategories) console.log('  -', c);
    }
  } finally {
    await api.shutdown();
  }
}

async function buildExistingRuleSignatures() {
  const rules = await api.getRules();
  return new Set(rules.map(signatureOf));
}

function signatureOf(rule) {
  return JSON.stringify({ stage: rule.stage, conditionsOp: rule.conditionsOp, conditions: rule.conditions, actions: rule.actions });
}

async function createRuleIfNew(rule, existingSignatures) {
  const sig = signatureOf(rule);
  if (existingSignatures.has(sig)) return false;
  await api.createRule(rule);
  existingSignatures.add(sig);
  return true;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
