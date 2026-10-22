import { Loader } from "@/components/ui/Loader";

/** Affiché pendant le chargement d'une route (navigation, démarrage à froid du container). */
export default function Loading() {
  return (
    <div className="page">
      <Loader page />
    </div>
  );
}
