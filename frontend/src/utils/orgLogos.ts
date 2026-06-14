// Logos das federações/conectores (arquivos em public/logo_federacao/).
// Federações são mapeadas pelo NOME oficial (igual ao arquivo); conectores pela sigla.
// As extensões variam (jpg/png/webp), por isso o nome do arquivo é explícito.

const BY_NAME: Record<string, string> = {
  'Associação Desportiva de Tênis do Estado do Rio de Janeiro': 'Associação Desportiva de Tênis do Estado do Rio de Janeiro.jpg',
  'Federação Acreana de Tênis': 'Federação Acreana de Tênis.jpg',
  'Federação Alagoana de Tênis': 'Federação Alagoana de Tênis.jpg',
  'Federação Amazonense de Tênis': 'Federação Amazonense de Tênis.jpg',
  'Federação Amapaense de Tênis': 'Federação Amapaense de Tênis.jpg',
  'Federação Bahiana de Tênis': 'Federação Bahiana de Tênis.jpg',
  'Federação Cearense de Tênis': 'Federação Cearense de Tênis.jpg',
  'Federação Brasiliense de Tênis': 'Federação Brasiliense de Tênis.jpg',
  'Federação Espírito-Santense de Tênis': 'Federação Espírito-Santense de Tênis.jpg',
  'Federação Goiana de Tênis': 'Federação Goiana de Tênis.jpg',
  'Federação Maranhense de Tênis': 'Federação Maranhense de Tênis.jpg',
  'Federação Mineira de Tênis e Beach Tennis': 'Federação Mineira de Tênis e Beach Tennis.png',
  'Federação Sul-Matogrossense de Tênis': 'Federação Sul-Matogrossense de Tênis.jpg',
  'Federação Mato-grossense de Tênis': 'Federação Mato-grossense de Tênis.jpg',
  'Federação Paraense de Tênis': 'Federação Paraense de Tênis.png',
  'Federação Paraibana de Tênis': 'Federação Paraibana de Tênis.png',
  'Federação Pernambucana de Tênis': 'Federação Pernambucana de Tênis.jpg',
  'Federação de Tênis e Beach Tênis do Piauí': 'Federação de Tênis e Beach Tênis do Piauí.jpg',
  'Federação Paranaense de Tênis': 'Federação Paranaense de Tênis.jpg',
  'Federação Potiguar de Tênis': 'Federação Potiguar de Tênis.jpg',
  'Federação Rondoniense de Tênis': 'Federação Rondoniense de Tênis.jpg',
  'Federação Roraimense de Tênis e Beach Tennis': 'Federação Roraimense de Tênis e Beach Tennis.jpg',
  'Federação Gaúcha de Tênis': 'Federação Gaúcha de Tênis.jpg',
  'Federação Catarinense de Tênis': 'Federação Catarinense de Tênis.jpg',
  'Federação Sergipana de Tênis': 'Federação Sergipana de Tênis.jpg',
  'Federação Paulista de Tênis': 'FPT.jpg',
  'Federação Tocantinense de Tênis': 'Federação Tocantinense de Tênis.jpg',
};

const BY_SHORT: Record<string, string> = {
  CBT: 'CBT.jpg',
  COSAT: 'COSAT.jpg',
  FPT: 'FPT.jpg',
  UTR: 'utr.png',
};

/** URL pública do logo da organização (federação por nome oficial, conector por sigla),
 *  ou null quando não há logo conhecido (ex.: ITF usa o asset embutido). */
export function orgLogoUrl(name?: string | null, short?: string | null): string | null {
  const file =
    (name && BY_NAME[name.trim()]) ||
    (short && BY_SHORT[short.trim().toUpperCase()]);
  return file ? `/logo_federacao/${encodeURIComponent(file)}` : null;
}