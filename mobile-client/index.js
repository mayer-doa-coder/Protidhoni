/**
 * @format
 */

// Must be the very first import: polyfills global.crypto.getRandomValues,
// which @noble/ed25519's key generation (src/crypto/identity.ts) needs and
// Hermes does not provide out of the box.
import 'react-native-get-random-values';

import { AppRegistry } from 'react-native';
import App from './App';
import { name as appName } from './app.json';

AppRegistry.registerComponent(appName, () => App);
