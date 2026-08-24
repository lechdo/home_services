const api = require('@actual-app/api');

async function buildCategoryIndex() {
  const groups = await api.getCategoryGroups();
  const index = new Map();
  for (const group of groups) {
    for (const cat of group.categories) {
      index.set(`${group.name} > ${cat.name}`, cat.id);
    }
  }
  return index;
}

async function resolveAccountId(accountName) {
  const accounts = await api.getAccounts();
  if (!accountName) return accounts[0].id;
  const found = accounts.find((a) => a.name === accountName);
  if (!found) throw new Error(`Compte "${accountName}" introuvable`);
  return found.id;
}

function requireCategory(index, categoryPath, missing) {
  const id = index.get(categoryPath);
  if (!id) missing.add(categoryPath);
  return id;
}

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`Variable d'environnement manquante : ${name}`);
    process.exit(1);
  }
  return value;
}

// Reproduit l'évaluation "contains" / "doesNotContain" du moteur de règles Actual :
// comparaison insensible à la casse (toLowerCase des deux côtés), sans autre normalisation.
function payeeMatches(fieldValue, keyword, exclude) {
  const value = String(fieldValue || '').toLowerCase();
  if (!value.includes(keyword.toLowerCase())) return false;
  for (const ex of exclude || []) {
    if (value.includes(ex.toLowerCase())) return false;
  }
  return true;
}

module.exports = { api, buildCategoryIndex, resolveAccountId, requireCategory, requireEnv, payeeMatches };
