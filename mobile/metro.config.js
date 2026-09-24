// Metro only watches files under the project root by default, and
// packages/shared lives one level up beside web/. Without watchFolders the
// `@shared/*` imports resolve in TypeScript but fail at bundle time with
// "Unable to resolve module", which reads like a typo rather than a config gap.
//
// Nothing else is overridden. An earlier version of this file also set
// `nodeModulesPaths` and `disableHierarchicalLookup`, which expo-doctor flags
// as unsafe -- and they were the reason transitive packages kept failing to
// resolve during setup.
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const projectRoot = __dirname;
const sharedRoot = path.resolve(projectRoot, '..', 'packages', 'shared');

const config = getDefaultConfig(projectRoot);

config.watchFolders = [sharedRoot];
config.resolver.extraNodeModules = {
  ...config.resolver.extraNodeModules,
  '@shared': path.resolve(sharedRoot, 'src'),
};

module.exports = config;
