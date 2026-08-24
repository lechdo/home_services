// Applique rétroactivement le fichier de règles aux transactions déjà importées
// AVANT la création des règles (l'API Actual ne rejoue pas les règles sur les
// transactions existantes — seules les nouvelles transactions importées après
// coup en bénéficient automatiquement). Ne touche que les transactions dont la
// catégorie est actuellement vide, pour ne jamais écraser une catégorisation
// manuelle déjà faite par l'utilisateur.
//
// Usage : identique à apply-rules.js (mêmes variables d'environnement),
// à lancer après apply-rules.js.
//   node categorize-existing.js rules.test.json

const path = require('path');
const fs = require('fs');
const { api, buildCategoryIndex, resolveAccountId, requireCategory, requireEnv, payeeMatches } = require('./lib');

async function main() {
  const rulesFile = process.argv[2];
  if (!rulesFile) {
    console.error('Usage: node categorize-existing.js <rules-file.json>');
    process.exit(1);
  }

  const spec = JSON.parse(fs.readFileSync(rulesFile, 'utf8'));

  await api.init({
    dataDir: path.join(__dirname, '.cache'),
    serverURL: process.env.ACTUAL_SERVER_URL || 'http://127.0.0.1:8083',
    password: requireEnv('ACTUAL_PASSWORD'),
  });

  await api.downloadBudget(requireEnv('ACTUAL_SYNC_ID'));

  try {
    const categoryIdByPath = await buildCategoryIndex();
    const accountId = await resolveAccountId(spec.account);
    const missingCategories = new Set();

    const catchAllCategoryId = spec.catchAllCategory
      ? requireCategory(categoryIdByPath, spec.catchAllCategory, missingCategories)
      : null;

    const transactions = await api.getTransactions(accountId, '1970-01-01', '2100-01-01');
    const uncategorized = transactions.filter((t) => !t.category && !t.is_parent);

    const assignments = new Map();
    if (catchAllCategoryId) {
      for (const t of uncategorized) assignments.set(t.id, catchAllCategoryId);
    }

    for (const entry of spec.rules) {
      const categoryId = requireCategory(categoryIdByPath, entry.category, missingCategories);
      if (!categoryId) continue;
      const field = entry.field || 'imported_payee';

      for (const t of uncategorized) {
        const fieldValue = t[field];
        const matches = entry.keywords.some((kw) => payeeMatches(fieldValue, kw, entry.exclude));
        if (matches) assignments.set(t.id, categoryId);
      }
    }

    let updated = 0;
    for (const [id, categoryId] of assignments) {
      await api.updateTransaction(id, { category: categoryId });
      updated++;
    }

    console.log(`Transactions initialement sans catégorie : ${uncategorized.length}`);
    console.log(`Transactions recatégorisées : ${updated}`);
    if (missingCategories.size > 0) {
      console.log('Catégories introuvables :');
      for (const c of missingCategories) console.log('  -', c);
    }
  } finally {
    await api.shutdown();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
