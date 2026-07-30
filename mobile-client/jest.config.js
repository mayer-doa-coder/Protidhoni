module.exports = {
  preset: '@react-native/jest-preset',
  // @noble/* and canonicalize ship as pure ESM ("type": "module") with no
  // CommonJS build; the preset's default transformIgnorePatterns only lets
  // react-native/@react-native* packages through babel-jest, so without this
  // addition Jest would try to `require()` them directly and fail with
  // ERR_REQUIRE_ESM. @op-engineering/op-sqlite is a native module that is
  // always mocked in tests (see src/db/__mocks__), so it does not need to be
  // added here.
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community|-async-storage)?|@noble|canonicalize)/)',
  ],
  moduleNameMapper: {
    '^@react-native-async-storage/async-storage$':
      '<rootDir>/node_modules/@react-native-async-storage/async-storage/lib/module/jest/AsyncStorageMock.js',
    // The RN preset's custom Jest resolver does not resolve package.json
    // "exports" maps for plain third-party packages; canonicalize ships
    // only an "exports"-based entry point (no top-level "module"/"browser"
    // fallback Jest's resolver understands), so point straight at the file.
    '^canonicalize$': '<rootDir>/node_modules/canonicalize/lib/canonicalize.js',
  },
};
