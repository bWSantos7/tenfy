// Tipagem mínima para as variáveis EXPO_PUBLIC_* lidas via process.env.
// O Metro/Babel do Expo substitui esses acessos pelo valor literal em build time;
// esta declaração existe só para satisfazer o TypeScript (sem depender de @types/node).
declare const process: {
  env: {
    EXPO_PUBLIC_WEB_URL?: string;
    EXPO_PUBLIC_API_BASE_URL?: string;
    [key: string]: string | undefined;
  };
};
