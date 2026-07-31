import * as RNFS from "@dr.pogodin/react-native-fs";

/**
 * Copies a large bundled Android asset (LLM checkpoint, offline map tiles)
 * out to a real file the device's filesystem, once. Both llama.cpp (mmap)
 * and SQLite (mbtiles is a SQLite file) need a genuine file path — an
 * android_asset:// URI inside the compressed APK is not mmap-able by native
 * code that isn't going through Android's AssetManager APIs.
 */
export async function ensureAssetCopiedToStorage(
  assetPath: string,
  fileName: string,
  onProgress?: (detail: string) => void,
): Promise<string> {
  const destDir = `${RNFS.DocumentDirectoryPath}/offline-assets`;
  const destPath = `${destDir}/${fileName}`;

  if (await RNFS.exists(destPath)) return destPath;

  onProgress?.(`Copying ${fileName} to local storage (first run only)…`);
  if (!(await RNFS.exists(destDir))) {
    await RNFS.mkdir(destDir);
  }
  await RNFS.copyFileAssets(assetPath, destPath);
  return destPath;
}
