import Nav from "@/components/nav";
import Hero from "@/components/hero";
import TrustMarquee from "@/components/trust-marquee";
import BentoGrid from "@/components/bento-grid";
import IndustryTabs from "@/components/industry-tabs";
import Footer from "@/components/footer";

export default function Home() {
  return (
    <main className="relative min-h-screen bg-canvas">
      <Nav />
      <Hero />
      <TrustMarquee />
      <BentoGrid />
      <IndustryTabs />
      <Footer />
    </main>
  );
}
