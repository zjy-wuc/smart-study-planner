import "@/components/css/LandscapeScene.css";

type LandscapeSceneProps = {
  variant: "mountains" | "ocean";
};

/** 页面装饰背景；与内容分层，不读取数据或接收用户操作。 */
export function LandscapeScene({ variant }: LandscapeSceneProps) {
  return (
    <div className={`landscape-scene landscape-scene--${variant}`} aria-hidden="true">
      <span className="landscape-scene-light" />
      <span className="landscape-scene-cloud" />
      <span className="landscape-scene-art" />
    </div>
  );
}
