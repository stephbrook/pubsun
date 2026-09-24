import { Lookup } from "./components/lookup";

export default function Home() {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col px-5 py-14 sm:px-8 sm:py-20">
      <header>
        <h1 className="text-4xl leading-none tracking-tight text-ink sm:text-5xl">
          Schooner Weather
        </h1>
        <p className="mt-3 max-w-md text-muted">
          Type a pub. See which side is in the sun.
        </p>
      </header>
      <Lookup />
      <footer className="mt-16 border-t border-rule pt-5 text-sm text-muted">
        Google Places · Google Solar · OpenStreetMap · Melbourne time
      </footer>
    </div>
  );
}
